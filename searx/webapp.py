#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebbApp

"""
# pylint: disable=use-dict-literal
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys

from timeit import default_timer
from html import escape
from io import StringIO

import urllib
import urllib.parse
from urllib.parse import urlencode, urlparse, unquote

import warnings
import httpx

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter  # pylint: disable=no-name-in-module

import flask

from flask import (
    Flask,
    render_template,
    url_for,
    make_response,
    redirect,
    send_from_directory,
)
from flask.wrappers import Response
from flask.json import jsonify

from flask_babel import (
    Babel,
    gettext,
    format_decimal,
)

from searx.extended_types import sxng_request, SXNG_Request
from searx import (
    logger,
    get_setting,
    searx_debug,
)

import searx.preferences
import searx.client
import searx.answerers
import searx.locales
import searx.plugins
import searx.search
import searx.engines

from searx import infopage
from searx import limiter
from searx.botdetection import link_token

from searx.data import ENGINE_DESCRIPTIONS
from searx.result_types import Answer
from searx.settings_defaults import OUTPUT_FORMATS
from searx.settings_loader import DEFAULT_SETTINGS_FILE
from searx.exceptions import SearxParameterException

from searx import webutils
from searx.webutils import (
    highlight_content,
    get_result_templates,
    get_themes,
    exception_classname_to_text,
    new_hmac,
    is_hmac_of,
    is_flask_run_cmdline,
    group_engines_in_tab,
    custom_url_for,
)
from searx.utils import gen_useragent, dict_subset
from searx.version import VERSION_STRING, GIT_URL, GIT_BRANCH
from searx.query import RawTextQuery


from searx.metrics import get_engines_stats, get_engine_errors, get_reliabilities, histogram, counter, openmetrics
from searx.flaskfix import patch_application
from searx.autocomplete import search_autocomplete
from searx import favicons
from searx.redisdb import initialize as redis_initialize
from searx.network import stream as http_stream, set_context_network_name
from searx.search.checker import get_result as checker_get_result


logger = logger.getChild('webapp')

warnings.simplefilter("always")

# check secret_key
if not searx_debug and get_setting("server.secret_key") == 'ultrasecretkey':
    logger.error('server.secret_key is not changed. Please use something else instead of ultrasecretkey.')
    sys.exit(1)

# about templates
logger.debug('templates directory is %s', get_setting("ui.templates_path"))
default_theme = get_setting("ui.default_theme")
templates_path = get_setting("ui.templates_path")
themes = get_themes(templates_path)
result_templates = get_result_templates(templates_path)

STATS_SORT_PARAMETERS = {
    'name': (False, 'name', ''),
    'score': (True, 'score_per_result', 0),
    'result_count': (True, 'result_count', 0),
    'time': (False, 'total', 0),
    'reliability': (False, 'reliability', 100),
}

# Flask app
app = Flask(__name__, static_folder=get_setting("ui.static_path"), template_folder=templates_path)

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.jinja_env.add_extension('jinja2.ext.loopcontrols')  # pylint: disable=no-member
app.jinja_env.filters['group_engines_in_tab'] = group_engines_in_tab  # pylint: disable=no-member
app.secret_key = get_setting("server.secret_key")

_ = Babel(app, locale_selector=searx.locales.babel_locale_selector)


def _get_locale_rfc5646(locale):
    """Get locale name for <html lang="...">
    Chrom* browsers don't detect the language when there is a subtag (ie a territory).
    For example "zh-TW" is detected but not "zh-Hant-TW".
    This function returns a locale without the subtag.
    """
    parts = locale.split('-')
    return parts[0].lower() + '-' + parts[-1].upper()


# code-highlighter
@app.template_filter('code_highlighter')
def code_highlighter(codelines, language=None):
    if not language:
        language = 'text'

    try:
        # find lexer by programming language
        lexer = get_lexer_by_name(language, stripall=True)

    except Exception as e:  # pylint: disable=broad-except
        logger.warning("pygments lexer: %s " % e)
        # if lexer is not found, using default one
        lexer = get_lexer_by_name('text', stripall=True)

    html_code = ''
    tmp_code = ''
    last_line = None
    line_code_start = None

    # parse lines
    for line, code in codelines:
        if not last_line:
            line_code_start = line

        # new codeblock is detected
        if last_line is not None and last_line + 1 != line:

            # highlight last codepart
            formatter = HtmlFormatter(linenos='inline', linenostart=line_code_start, cssclass="code-highlight")
            html_code = html_code + highlight(tmp_code, lexer, formatter)

            # reset conditions for next codepart
            tmp_code = ''
            line_code_start = line

        # add codepart
        tmp_code += code + '\n'

        # update line
        last_line = line

    # highlight last codepart
    formatter = HtmlFormatter(linenos='inline', linenostart=line_code_start, cssclass="code-highlight")
    html_code = html_code + highlight(tmp_code, lexer, formatter)

    return html_code


def get_result_template(theme_name: str, template_name: str):
    themed_path = theme_name + '/result_templates/' + template_name
    if themed_path in result_templates:
        return themed_path
    return 'result_templates/' + template_name


def morty_proxify(url: str):
    if url.startswith('//'):
        url = 'https:' + url

    if not get_setting("result_proxy.url"):
        return url

    url_params = dict(mortyurl=url)

    if get_setting("result_proxy.key"):
        url_params['mortyhash'] = hmac.new(get_setting("result_proxy.key"), url.encode(), hashlib.sha256).hexdigest()

    return '{0}?{1}'.format(get_setting("result_proxy.url"), urlencode(url_params))


def image_proxify(url: str):

    if url.startswith('//'):
        url = 'https:' + url

    if not sxng_request.preferences.fields.image_proxy.value:
        return url

    if url.startswith('data:image/'):
        # 50 is an arbitrary number to get only the beginning of the image.
        partial_base64 = url[len('data:image/') : 50].split(';')
        if (
            len(partial_base64) == 2
            and partial_base64[0] in ['gif', 'png', 'jpeg', 'pjpeg', 'webp', 'tiff', 'bmp']
            and partial_base64[1].startswith('base64,')
        ):
            return url
        return None

    if get_setting("result_proxy.url"):
        return morty_proxify(url)

    h = new_hmac(get_setting("server.secret_key"), url.encode())

    return '{0}?{1}'.format(url_for('image_proxy'), urlencode(dict(url=url.encode(), h=h)))


def get_pretty_url(parsed_url: urllib.parse.ParseResult):
    url_formatting_pref = sxng_request.preferences.fields.url_formatting.value

    if url_formatting_pref == 'full':
        return [parsed_url.geturl()]

    if url_formatting_pref == 'host':
        return [parsed_url.netloc]

    path = parsed_url.path
    path = path[:-1] if len(path) > 0 and path[-1] == '/' else path
    path = unquote(path.replace("/", " › "))
    return [parsed_url.scheme + "://" + parsed_url.netloc, path]


def render(template_name: str, **kwargs):

    kwargs["get_setting"] = get_setting
    kwargs["PREF"] = sxng_request.preferences
    kwargs["CLIENT"] = sxng_request.client

    # values from the HTTP requests
    kwargs['endpoint'] = 'results' if 'q' in kwargs else sxng_request.endpoint
    kwargs['cookies'] = sxng_request.cookies
    kwargs['errors'] = sxng_request.errors
    kwargs['link_token'] = link_token.get_token()

    kwargs['DEFAULT_CATEGORY'] = searx.engines.DEFAULT_CATEGORY

    # values from settings
    kwargs['search_formats'] = [x for x in get_setting("search.formats") if x != 'html']
    kwargs['instance_name'] = get_setting('general.instance_name')
    kwargs['searx_version'] = VERSION_STRING
    kwargs['searx_git_url'] = GIT_URL
    kwargs['enable_metrics'] = get_setting('general.enable_metrics')
    kwargs['get_pretty_url'] = get_pretty_url

    # values from settings: donation_url
    donation_url = get_setting('general.donation_url')
    if donation_url is True:
        donation_url = custom_url_for('info', pagename='donate')
    kwargs['donation_url'] = donation_url

    # helpers to create links to other pages
    kwargs['url_for'] = custom_url_for  # override url_for function in templates
    kwargs['image_proxify'] = image_proxify
    kwargs['favicon_url'] = favicons.favicon_url
    kwargs['proxify'] = morty_proxify if get_setting("result_proxy.url") is not None else None
    kwargs['proxify_results'] = get_setting("result_proxy.proxify_results")
    kwargs['cache_url'] = get_setting("ui.cache_url")
    kwargs['get_result_template'] = get_result_template
    kwargs['opensearch_url'] = (
        url_for('opensearch')
        + '?'
        + urlencode(
            {
                'method': sxng_request.preferences.fields.method.value,
                'autocomplete': sxng_request.preferences.fields.autocomplete.value,
            }
        )
    )
    kwargs['urlparse'] = urlparse

    start_time = default_timer()
    result = render_template('{}/{}'.format(kwargs['theme'], template_name), **kwargs)
    sxng_request.render_time += default_timer() - start_time  # pylint: disable=assigning-non-slot

    return result


@app.before_request
def pre_request():
    SXNG_Request.init()


@app.after_request
def add_default_headers(response: flask.Response):
    # set default http headers
    for header, value in get_setting("server.default_http_headers").items():
        if header in response.headers:
            continue
        response.headers[header] = value
    return response


@app.after_request
def post_request(response: flask.Response):
    total_time = default_timer() - sxng_request.start_time
    timings_all = [
        'total;dur=' + str(round(total_time * 1000, 3)),
        'render;dur=' + str(round(sxng_request.render_time * 1000, 3)),
    ]
    if len(sxng_request.timings) > 0:
        timings = sorted(sxng_request.timings, key=lambda t: t.total)
        timings_total = [
            'total_' + str(i) + '_' + t.engine + ';dur=' + str(round(t.total * 1000, 3)) for i, t in enumerate(timings)
        ]
        timings_load = [
            'load_' + str(i) + '_' + t.engine + ';dur=' + str(round(t.load * 1000, 3))
            for i, t in enumerate(timings)
            if t.load
        ]
        timings_all = timings_all + timings_total + timings_load
    response.headers.add('Server-Timing', ', '.join(timings_all))
    return response


def index_error(output_format: str, error_message: str):
    if output_format == 'json':
        return Response(json.dumps({'error': error_message}), mimetype='application/json')
    if output_format == 'csv':
        response = Response('', mimetype='application/csv')
        cont_disp = 'attachment;Filename=searx.csv'
        response.headers.add('Content-Disposition', cont_disp)
        return response

    if output_format == 'rss':
        response_rss = render(
            'opensearch_response_rss.xml',
            results=[],
            q=sxng_request.form['q'] if 'q' in sxng_request.form else '',
            number_of_results=0,
            error_message=error_message,
        )
        return Response(response_rss, mimetype='text/xml')

    # html
    sxng_request.errors.append(gettext('search error'))
    return render("index.html")


@app.route('/', methods=['GET', 'POST'])
def index():
    """Render index page."""

    # redirect to search if there's a query in the request
    if sxng_request.form.get('q'):
        query = ('?' + sxng_request.query_string.decode()) if sxng_request.query_string else ''
        return redirect(url_for('search') + query, 308)

    return render("index.html")


@app.route('/healthz', methods=['GET'])
def health():
    return Response('OK', mimetype='text/plain')


@app.route('/client<token>.css', methods=['GET', 'POST'])
def client_token(token=None):
    link_token.ping(sxng_request, token)
    return Response('', mimetype='text/css', headers={"Cache-Control": "no-store, max-age=0"})


@app.route('/rss.xsl', methods=['GET', 'POST'])
def rss_xsl():
    return render_template(
        f"{sxng_request.preferences.fields.theme.value}/rss.xsl",
        url_for=custom_url_for,
    )


@app.route('/search', methods=['GET', 'POST'])
def search():
    """Search query in q and return results.

    Supported outputs: html, json, csv, rss.
    """
    # pylint: disable=too-many-locals, too-many-return-statements, too-many-branches
    # pylint: disable=too-many-statements

    # output_format
    output_format = sxng_request.form.get('format', 'html')
    if output_format not in OUTPUT_FORMATS:
        output_format = 'html'

    if output_format not in get_setting("search.formats"):
        flask.abort(403)

    # check if there is query (not None and not an empty string)
    if not sxng_request.form.get('q'):
        if output_format == 'html':
            return render("index.html")
        return index_error(output_format, 'No query'), 400

    try:
        search_query = sxng_request.client.get_search_query()
        search_obj = searx.search.SearchWithPlugins(search_query, sxng_request)
        result_container = search_obj.search()

    except SearxParameterException as e:
        logger.exception('search error: SearxParameterException')
        return index_error(output_format, e.message), 400
    except Exception as e:  # pylint: disable=broad-except
        logger.exception(e, exc_info=True)
        return index_error(output_format, gettext('search error')), 500

    # 1. check if the result is a redirect for an external bang
    if result_container.redirect_url:
        return redirect(result_container.redirect_url)

    # 2. add Server-Timing header for measuring performance characteristics of
    # web applications
    sxng_request.timings = result_container.get_timings()  # pylint: disable=assigning-non-slot

    # 3. formats without a template

    if output_format == 'json':

        response = webutils.get_json_response(search_query, result_container)
        return Response(response, mimetype='application/json')

    if output_format == 'csv':

        csv = webutils.CSVWriter(StringIO())
        webutils.write_csv_response(csv, result_container)
        csv.stream.seek(0)

        response = Response(csv.stream.read(), mimetype='application/csv')
        cont_disp = 'attachment;Filename=searx_-_{0}.csv'.format(search_query.query)
        response.headers.add('Content-Disposition', cont_disp)
        return response

    # 4. formats rendered by a template / RSS & HTML

    current_template = None
    previous_result = None

    results = result_container.get_ordered_results()

    if search_query.redirect_to_first_result and results:
        return redirect(results[0]['url'], 302)

    for result in results:
        if output_format == 'html':
            if 'content' in result and result['content']:
                result['content'] = highlight_content(escape(result['content'][:1024]), search_query.query)
            if 'title' in result and result['title']:
                result['title'] = highlight_content(escape(result['title'] or ''), search_query.query)

        if getattr(result, 'publishedDate', None):  # do not try to get a date from an empty string or a None type
            try:  # test if publishedDate >= 1900 (datetime module bug)
                result['pubdate'] = result['publishedDate'].strftime('%Y-%m-%d %H:%M:%S%z')
            except ValueError:
                result['publishedDate'] = None
            else:
                result['publishedDate'] = webutils.searxng_l10n_timespan(result['publishedDate'])

        # set result['open_group'] = True when the template changes from the previous result
        # set result['close_group'] = True when the template changes on the next result
        if current_template != result.template:
            result.open_group = True
            if previous_result:
                previous_result.close_group = True  # pylint: disable=unsupported-assignment-operation
        current_template = result.template
        previous_result = result

    if previous_result:
        previous_result.close_group = True

    # 4.a RSS

    if output_format == 'rss':
        response_rss = render(
            'opensearch_response_rss.xml',
            results=results,
            q=sxng_request.form['q'],
            number_of_results=result_container.number_of_results,
        )
        return Response(response_rss, mimetype='text/xml')

    # 4.b HTML

    # suggestions: use RawTextQuery to get the suggestion URLs with the same bang
    suggestion_urls = list(
        map(
            lambda suggestion: {
                'url': sxng_request.client.raw_query.changeQuery(suggestion).getFullQuery(),
                'title': suggestion,
            },
            result_container.suggestions,
        )
    )

    correction_urls = list(
        map(
            lambda correction: {
                'url': sxng_request.client.raw_query.changeQuery(correction).getFullQuery(),
                'title': correction,
            },
            result_container.corrections,
        )
    )

    # engine_timings: get engine response times sorted from slowest to fastest
    engine_timings = sorted(result_container.get_timings(), reverse=True, key=lambda e: e.total)
    max_response_time = engine_timings[0].total if engine_timings else None
    engine_timings_pairs = [(timing.engine, timing.total) for timing in engine_timings]

    # search_query.lang contains the user choice (all, auto, en, ...)
    # when the user choice is "auto", search.search_query.lang contains the detected language
    # otherwise it is equals to search_query.lang
    return render(
        "results.html",
        results=results,
        q=sxng_request.form['q'],
        time_range=search_query.time_range or '',
        number_of_results=format_decimal(result_container.number_of_results),
        suggestions=suggestion_urls,
        answers=result_container.answers,
        corrections=correction_urls,
        infoboxes=result_container.infoboxes,
        engine_data=result_container.engine_data,
        paging=result_container.paging,
        unresponsive_engines=webutils.get_translated_errors(result_container.unresponsive_engines),
        timeout_limit=sxng_request.form.get('timeout_limit', None),
        timings=engine_timings_pairs,
        max_response_time=max_response_time,
    )


@app.route('/about', methods=['GET'])
def about():
    """Redirect to about page"""
    # custom_url_for is going to add the locale
    return redirect(custom_url_for('info', pagename='about'))


@app.route('/info/<locale>/<pagename>', methods=['GET'])
def info(pagename, locale):
    """Render page of online user documentation"""
    page = infopage.INFO_PAGES.get_page(pagename, locale)
    if page is None:
        flask.abort(404)

    user_locale = sxng_request.preferences.fields.ui_locale_tag.value
    return render(
        'info.html',
        all_pages=infopage.INFO_PAGES.iter_pages(user_locale, fallback_to_default=True),
        active_page=page,
        active_pagename=pagename,
    )


@app.route('/autocompleter', methods=['GET', 'POST'])
def autocompleter():
    """Return autocompleter results"""

    # run autocompleter
    results = []

    # parse query
    raw_text_query = RawTextQuery(
        sxng_request.form.get('q', ''),
        sxng_request.preferences.fields.engines.disabled_engines,
    )
    sug_prefix = raw_text_query.getQuery()

    for obj in searx.answerers.STORAGE.ask(sug_prefix):
        if isinstance(obj, Answer):
            results.append(obj.answer)

    # normal autocompletion results only appear if no inner results returned
    # and there is a query part
    if len(raw_text_query.autocomplete_list) == 0 and len(sug_prefix) > 0:

        # get SearXNG's locale and autocomplete backend from cookie
        sxng_locale = sxng_request.preferences.fields.ui_locale_tag.value
        backend_name = sxng_request.preferences.fields.autocomplete.value

        for result in search_autocomplete(backend_name, sug_prefix, sxng_locale):
            # attention: this loop will change raw_text_query object and this is
            # the reason why the sug_prefix was stored before (see above)
            if result != sug_prefix:
                results.append(raw_text_query.changeQuery(result).getFullQuery())

    if len(raw_text_query.autocomplete_list) > 0:
        for autocomplete_text in raw_text_query.autocomplete_list:
            results.append(raw_text_query.get_autocomplete_full_query(autocomplete_text))

    if sxng_request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # the suggestion request comes from the searx search form
        suggestions = json.dumps(results)
        mimetype = 'application/json'
    else:
        # the suggestion request comes from browser's URL bar
        suggestions = json.dumps([sug_prefix, results])
        mimetype = 'application/x-suggestions+json'

    suggestions = escape(suggestions, False)
    return Response(suggestions, mimetype=mimetype)


@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    """Render preferences page && save user preferences"""

    # pylint: disable=too-many-locals, too-many-return-statements, too-many-branches
    # pylint: disable=too-many-statements

    # save preferences using the link the /preferences?preferences=...
    if sxng_request.args.get("preferences") or sxng_request.form.get("preferences"):
        resp = make_response(redirect(url_for('index', _external=True)))
        sxng_request.preferences.save_cookie(resp)
        return resp

    # save preferences
    if sxng_request.method == 'POST':
        resp = make_response(redirect(url_for('index', _external=True)))
        try:
            sxng_request.preferences.parse_cookie(sxng_request)
        except ValueError:
            sxng_request.errors.append(gettext('Invalid settings, please edit your preferences'))
            return resp
        sxng_request.preferences.save_cookie(resp)
        return resp

    # render preferences

    img_proxy = sxng_request.preferences.fields.image_proxy.value

    # stats for preferences page

    # get first element [0], the engine time, and then the second element [1] :
    # the time (the first one is the label)
    stats = {}  # pylint: disable=redefined-outer-name
    max_rate95 = 0

    eng_list = [searx.engines.engines[e] for e in sxng_request.preferences.fields.engines.members.keys()]

    for e in eng_list:
        h = histogram('engine', e.name, 'time', 'total')
        median = round(h.percentage(50), 1) if h.count > 0 else None
        rate80 = round(h.percentage(80), 1) if h.count > 0 else None
        rate95 = round(h.percentage(95), 1) if h.count > 0 else None

        max_rate95 = max(max_rate95, rate95 or 0)

        result_count_sum = histogram('engine', e.name, 'result', 'count').sum
        successful_count = counter('engine', e.name, 'search', 'count', 'successful')
        result_count = int(result_count_sum / float(successful_count)) if successful_count else 0

        stats[e.name] = {
            'time': median,
            'rate80': rate80,
            'rate95': rate95,
            'warn_timeout': e.timeout > get_setting("outgoing.request_timeout"),
            'supports_selected_language': e.traits.is_locale_supported(
                str(sxng_request.preferences.fields.search_locale_tag.value)
            ),
            'result_count': result_count,
        }

    # reliabilities

    reliabilities = {}
    engine_errors = get_engine_errors(eng_list)
    checker_results = checker_get_result()
    checker_results = (
        checker_results['engines'] if checker_results['status'] == 'ok' and 'engines' in checker_results else {}
    )

    for e in eng_list:
        checker_result = checker_results.get(e.name, {})
        checker_success = checker_result.get('success', True)
        errors = engine_errors.get(e.name) or []
        if counter('engine', e.name, 'search', 'count', 'sent') == 0:
            # no request
            reliability = None
        elif checker_success and not errors:
            reliability = 100
        elif 'simple' in checker_result.get('errors', {}):
            # the basic (simple) test doesn't work: the engine is broken according to the checker
            # even if there is no exception
            reliability = 0
        else:
            # pylint: disable=consider-using-generator
            reliability = 100 - sum([error['percentage'] for error in errors if not error.get('secondary')])

        reliabilities[e.name] = {
            'reliability': reliability,
            'errors': [],
            'checker': checker_results.get(e.name, {}).get('errors', {}).keys(),
        }
        # keep the order of the list checker_results[e.name]['errors'] and deduplicate.
        # the first element has the highest percentage rate.
        reliabilities_errors = []
        for error in errors:
            error_user_text = None
            if error.get('secondary') or 'exception_classname' not in error:
                continue
            error_user_text = exception_classname_to_text.get(error.get('exception_classname'))
            if not error:
                error_user_text = exception_classname_to_text[None]
            if error_user_text not in reliabilities_errors:
                reliabilities_errors.append(error_user_text)
        reliabilities[e.name]['errors'] = reliabilities_errors

    # supports

    supports = {}
    for e in eng_list:
        supports_selected_language = e.traits.is_locale_supported(
            sxng_request.preferences.fields.search_locale_tag.value
        )
        safesearch = e.safesearch
        time_range_support = e.time_range_support
        for checker_test_name in checker_results.get(e.name, {}).get('errors', {}):
            if supports_selected_language and checker_test_name.startswith('lang_'):
                supports_selected_language = '?'
            elif safesearch and checker_test_name == 'safesearch':
                safesearch = '?'
            elif time_range_support and checker_test_name == 'time_range':
                time_range_support = '?'
        supports[e.name] = {
            'supports_selected_language': supports_selected_language,
            'safesearch': safesearch,
            'time_range_support': time_range_support,
        }

    return render(
        "preferences.html",
        image_proxy=img_proxy,
        stats=stats,
        max_rate95=max_rate95,
        reliabilities=reliabilities,
        supports=supports,
        answer_storage=searx.answerers.STORAGE.info,
        shortcuts={y: x for x, y in searx.engines.engine_shortcuts.items()},
        themes=themes,
        plugins_storage=searx.plugins.STORAGE.info,
    )


app.add_url_rule('/favicon_proxy', methods=['GET'], endpoint="favicon_proxy", view_func=favicons.favicon_proxy)


@app.route('/image_proxy', methods=['GET'])
def image_proxy():
    # pylint: disable=too-many-return-statements, too-many-branches

    url = sxng_request.args.get('url')
    if not url:
        return '', 400

    if not is_hmac_of(get_setting("server.secret_key"), url.encode(), sxng_request.args.get('h', '')):
        return '', 400

    maximum_size = 5 * 1024 * 1024
    forward_resp = False
    resp = None
    try:
        request_headers = {
            'User-Agent': gen_useragent(),
            'Accept': 'image/webp,*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Sec-GPC': '1',
            'DNT': '1',
        }
        set_context_network_name('image_proxy')
        resp, stream = http_stream(method='GET', url=url, headers=request_headers, allow_redirects=True)
        content_length = resp.headers.get('Content-Length')
        if content_length and content_length.isdigit() and int(content_length) > maximum_size:
            return 'Max size', 400

        if resp.status_code != 200:
            logger.debug('image-proxy: wrong response code: %i', resp.status_code)
            if resp.status_code >= 400:
                return '', resp.status_code
            return '', 400

        if not resp.headers.get('Content-Type', '').startswith('image/') and not resp.headers.get(
            'Content-Type', ''
        ).startswith('binary/octet-stream'):
            logger.debug('image-proxy: wrong content-type: %s', resp.headers.get('Content-Type', ''))
            return '', 400

        forward_resp = True
    except httpx.HTTPError:
        logger.exception('HTTP error')
        return '', 400
    finally:
        if resp and not forward_resp:
            # the code is about to return an HTTP 400 error to the browser
            # we make sure to close the response between searxng and the HTTP server
            try:
                resp.close()
            except httpx.HTTPError:
                logger.exception('HTTP error on closing')

    def close_stream():
        nonlocal resp, stream
        try:
            if resp:
                resp.close()
            del resp
            del stream
        except httpx.HTTPError as e:
            logger.debug('Exception while closing response', e)

    try:
        headers = dict_subset(resp.headers, {'Content-Type', 'Content-Encoding', 'Content-Length', 'Length'})
        response = Response(stream, mimetype=resp.headers['Content-Type'], headers=headers, direct_passthrough=True)
        response.call_on_close(close_stream)
        return response
    except httpx.HTTPError:
        close_stream()
        return '', 400


@app.route('/engine_descriptions.json', methods=['GET'])
def engine_descriptions():
    lang = sxng_request.client.language_tag

    # FIXME: needs to be tested for zh-HK, zh-Hans-CN, zh-Hant-TW, fa-IR, nl-BE ..

    # by default the english description is used for all engines
    result = ENGINE_DESCRIPTIONS["en"].copy()
    if lang != "en":
        # if l10n exists, update engine's description
        for engine, description in ENGINE_DESCRIPTIONS.get(lang, {}).items():
            result[engine] = description

    # process items like:
    #     "gentoo":[
    #        "gentoo:en",
    #        "ref"
    #     ],

    for engine, description in result.items():

        if len(description) == 2 and description[1] == "ref":
            ref_engine, ref_lang = description[0].split(":")
            description = ENGINE_DESCRIPTIONS[ref_lang][ref_engine]

        if isinstance(description, str):
            description = [description, "wikipedia"]
        result[engine] = description

    # overwrite by about:description (from settings)

    for engine_name, engine_mod in searx.engines.engines.items():
        descr = getattr(engine_mod, "about", {}).get("description", None)
        if descr is not None:
            result[engine_name] = [descr, "SearXNG config"]

    return jsonify(result)


@app.route('/stats', methods=['GET'])
def stats():
    """Render engine statistics page."""
    sort_order = sxng_request.args.get('sort', default='name', type=str)
    selected_engine_name = sxng_request.args.get('engine', default=None, type=str)

    filtered_engines = dict(
        filter(lambda kv: sxng_request.preferences.validate_token(kv[1]), searx.engines.engines.items())
    )
    if selected_engine_name:
        if selected_engine_name not in filtered_engines:
            selected_engine_name = None
        else:
            filtered_engines = [selected_engine_name]

    checker_results = checker_get_result()
    checker_results = (
        checker_results['engines'] if checker_results['status'] == 'ok' and 'engines' in checker_results else {}
    )

    engine_stats = get_engines_stats(filtered_engines)
    engine_reliabilities = get_reliabilities(filtered_engines, checker_results)

    if sort_order not in STATS_SORT_PARAMETERS:
        sort_order = 'name'

    reverse, key_name, default_value = STATS_SORT_PARAMETERS[sort_order]

    def get_key(engine_stat):
        reliability = engine_reliabilities.get(engine_stat['name'], {}).get('reliability', 0)
        reliability_order = 0 if reliability else 1
        if key_name == 'reliability':
            key = reliability
            reliability_order = 0
        else:
            key = engine_stat.get(key_name) or default_value
            if reverse:
                reliability_order = 1 - reliability_order
        return (reliability_order, key, engine_stat['name'])

    technical_report = []
    for error in engine_reliabilities.get(selected_engine_name, {}).get('errors', []):
        technical_report.append(
            f"\
            Error: {error['exception_classname'] or error['log_message']} \
            Parameters: {error['log_parameters']} \
            File name: {error['filename'] }:{ error['line_no'] } \
            Error Function: {error['function']} \
            Code: {error['code']} \
            ".replace(
                ' ' * 12, ''
            ).strip()
        )
    technical_report = ' '.join(technical_report)

    engine_stats['time'] = sorted(engine_stats['time'], reverse=reverse, key=get_key)
    return render(
        # fmt: off
        'stats.html',
        sort_order = sort_order,
        engine_stats = engine_stats,
        engine_reliabilities = engine_reliabilities,
        selected_engine_name = selected_engine_name,
        searx_git_branch = GIT_BRANCH,
        technical_report = technical_report,
        # fmt: on
    )


@app.route('/stats/errors', methods=['GET'])
def stats_errors():
    filtered_engines = dict(
        filter(lambda kv: sxng_request.preferences.validate_token(kv[1]), searx.engines.engines.items())
    )
    result = get_engine_errors(filtered_engines)
    return jsonify(result)


@app.route('/stats/checker', methods=['GET'])
def stats_checker():
    result = checker_get_result()
    return jsonify(result)


@app.route('/metrics')
def stats_open_metrics():
    password = get_setting("general.open_metrics", None)

    if not (get_setting("general.enable_metrics", None) and password):
        return Response('open metrics is disabled', status=404, mimetype='text/plain')

    if not sxng_request.authorization or sxng_request.authorization.password != password:
        return Response('access forbidden', status=401, mimetype='text/plain')

    filtered_engines = dict(
        filter(lambda kv: sxng_request.preferences.validate_token(kv[1]), searx.engines.engines.items())
    )

    checker_results = checker_get_result()
    checker_results = (
        checker_results['engines'] if checker_results['status'] == 'ok' and 'engines' in checker_results else {}
    )

    engine_stats = get_engines_stats(filtered_engines)
    engine_reliabilities = get_reliabilities(filtered_engines, checker_results)
    metrics_text = openmetrics(engine_stats, engine_reliabilities)

    return Response(metrics_text, mimetype='text/plain')


@app.route('/robots.txt', methods=['GET'])
def robots():
    return Response(
        """User-agent: *
Allow: /info/en/about
Disallow: /stats
Disallow: /image_proxy
Disallow: /preferences
Disallow: /*?*q=*
""",
        mimetype='text/plain',
    )


@app.route('/opensearch.xml', methods=['GET'])
def opensearch():
    method = sxng_request.preferences.fields.method.value
    autocomplete = sxng_request.preferences.fields.autocomplete.value

    # chrome/chromium only supports HTTP GET....
    if sxng_request.headers.get('User-Agent', '').lower().find('webkit') >= 0:
        method = 'GET'

    if method not in ('POST', 'GET'):
        method = 'POST'

    ret = render('opensearch.xml', opensearch_method=method, autocomplete=autocomplete)
    resp = Response(response=ret, status=200, mimetype="application/opensearchdescription+xml")
    return resp


@app.route('/favicon.ico')
def favicon():
    theme = sxng_request.preferences.fields.theme.value
    return send_from_directory(
        os.path.join(app.root_path, get_setting("ui.static_path"), 'themes', theme, 'img'),
        'favicon.png',
        mimetype='image/vnd.microsoft.icon',
    )


@app.route('/clear_cookies')
def clear_cookies():
    resp = make_response(redirect(url_for('index', _external=True)))
    for cookie_name in sxng_request.cookies:
        resp.delete_cookie(cookie_name)
    return resp


@app.route('/config')
def config():
    """Return configuration in JSON format."""
    _engines = []
    for name, engine in searx.engines.engines.items():
        if not sxng_request.preferences.validate_token(engine):
            continue

        _languages = engine.traits.languages.keys()
        _engines.append(
            {
                'name': name,
                'categories': engine.categories,
                'shortcut': engine.shortcut,
                'enabled': not engine.disabled,
                'paging': engine.paging,
                'language_support': engine.language_support,
                'languages': list(_languages),
                'regions': list(engine.traits.regions.keys()),
                'safesearch': engine.safesearch,
                'time_range_support': engine.time_range_support,
                'timeout': engine.timeout,
            }
        )

    _plugins = [plg.info.__dict__ for plg in searx.plugins.STORAGE]
    _limiter_cfg = limiter.get_cfg()

    return jsonify(
        {
            'categories': list(searx.engines.categories.keys()),
            'engines': _engines,
            'plugins': _plugins,
            'instance_name': get_setting("general.instance_name"),
            'locales': searx.locales.LOCALE_NAMES,
            'default_locale': get_setting("ui.default_locale"),
            'autocomplete': get_setting("search.autocomplete"),
            'safe_search': get_setting("search.safe_search"),
            'default_theme': get_setting("ui.default_theme"),
            'version': VERSION_STRING,
            'brand': {
                'PRIVACYPOLICY_URL': get_setting('general.privacypolicy_url'),
                'CONTACT_URL': get_setting('general.contact_url'),
                'GIT_URL': GIT_URL,
                'GIT_BRANCH': GIT_BRANCH,
                'DOCS_URL': get_setting('brand.docs_url'),
            },
            'limiter': {
                'enabled': limiter.is_installed(),
                'botdetection.ip_limit.link_token': _limiter_cfg.get('botdetection.ip_limit.link_token'),
                'botdetection.ip_lists.pass_searxng_org': _limiter_cfg.get('botdetection.ip_lists.pass_searxng_org'),
            },
            'doi_resolvers': list(get_setting("doi_resolvers").keys()),
            'default_doi_resolver': get_setting("default_doi_resolver"),
            'public_instance': get_setting("server.public_instance"),
        }
    )


@app.errorhandler(404)
def page_not_found(_e):
    return render('404.html'), 404


# see https://flask.palletsprojects.com/en/1.1.x/cli/
# True if "FLASK_APP=searx/webapp.py FLASK_ENV=development flask run"
flask_run_development = (
    os.environ.get("FLASK_APP") is not None and os.environ.get("FLASK_ENV") == 'development' and is_flask_run_cmdline()
)

# True if reload feature is activated of werkzeug, False otherwise (including uwsgi, etc..)
#  __name__ != "__main__" if searx.webapp is imported (make test, make docs, uwsgi...)
# see run() at the end of this file : searx_debug activates the reload feature.
werkzeug_reloader = flask_run_development or (searx_debug and __name__ == "__main__")

# initialize the engines except on the first run of the werkzeug server.
if not werkzeug_reloader or (werkzeug_reloader and os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
    searx.locales.locales_initialize()
    redis_initialize()
    searx.plugins.initialize(app)
    searx.search.initialize(
        enable_checker=True,
        check_network=True,
        enable_metrics=get_setting("general.enable_metrics"),
    )
    limiter.initialize(app, searx.settings)
    favicons.init()


def run():
    logger.debug('starting webserver on %s:%s', get_setting("server.bind_address"), get_setting("server.port"))
    app.run(
        debug=searx_debug,
        use_debugger=searx_debug,
        port=get_setting("server.port"),
        host=get_setting("server.bind_address"),
        threaded=True,
        extra_files=[DEFAULT_SETTINGS_FILE],
    )


application = app
patch_application(app)

if __name__ == "__main__":
    run()
