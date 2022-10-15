# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""Bing (Web)

- https://github.com/searx/searx/issues/2019#issuecomment-648227442
"""
# pylint: disable=invalid-name

# FIXME: rewrite modul's doc-string


from typing import TYPE_CHECKING
import datetime
import re
import uuid
from urllib.parse import urlencode
from lxml import html
import babel
import babel.languages

from searx.utils import eval_xpath, extract_text, eval_xpath_list
from searx import network
from searx.locales import language_tag, region_tag
from searx.enginelib.traits import EngineTraits

if TYPE_CHECKING:
    import logging

    logger: logging.Logger

traits: EngineTraits

about = {
    "website": 'https://www.bing.com',
    "wikidata_id": 'Q182496',
    "official_api_documentation": 'https://www.microsoft.com/en-us/bing/apis/bing-web-search-api',
    "use_official_api": False,
    "require_api_key": False,
    "results": 'HTML',
}

send_accept_language_header = True
"""Bing tries to guess user's language and territory from the HTTP
Accept-Language.  Optional the user can select a search-language (can be
different to the UI language) and a region (market code)."""

# engine dependent config
categories = ['general', 'web']
paging = True
time_range_support = True
safesearch = True
safesearch_types = {2: 'STRICT', 1: 'DEMOTE', 0: 'OFF'}  # cookie: ADLT=STRICT

base_url = 'https://www.bing.com/search'
"""Bing (Web) search URL"""

bing_traits_url = 'https://learn.microsoft.com/en-us/bing/search-apis/bing-web-search/reference/market-codes'
"""Bing (Web) search API description"""


def _get_offset_from_pageno(pageno):
    return (pageno - 1) * 10 + 1


def set_bing_cookies(params, engine_language, engine_region, SID):

    # set cookies
    # -----------

    params['cookies']['_EDGE_V'] = '1'

    # _EDGE_S: F=1&SID=3A5253BD6BCA609509B741876AF961CA&mkt=zh-tw
    _EDGE_S = [
        'F=1',
        'SID=%s' % SID,
        'mkt=%s' % engine_region.lower(),
        'ui=%s' % engine_language.lower(),
    ]
    params['cookies']['_EDGE_S'] = '&'.join(_EDGE_S)
    logger.debug("cookie _EDGE_S=%s", params['cookies']['_EDGE_S'])

    # "_EDGE_CD": "m=zh-tw",

    _EDGE_CD = [  # pylint: disable=invalid-name
        'm=%s' % engine_region.lower(),  # search region: zh-cn
        'u=%s' % engine_language.lower(),  # UI: en-us
    ]

    params['cookies']['_EDGE_CD'] = '&'.join(_EDGE_CD) + ';'
    logger.debug("cookie _EDGE_CD=%s", params['cookies']['_EDGE_CD'])

    SRCHHPGUSR = [  # pylint: disable=invalid-name
        'SRCHLANG=%s' % engine_language,
        # Trying to set ADLT cookie here seems not to have any effect, I assume
        # there is some age verification by a cookie (and/or session ID) needed,
        # to disable the SafeSearch.
        'ADLT=%s' % safesearch_types.get(params['safesearch'], 'DEMOTE'),
    ]
    params['cookies']['SRCHHPGUSR'] = '&'.join(SRCHHPGUSR)
    logger.debug("cookie SRCHHPGUSR=%s", params['cookies']['SRCHHPGUSR'])


def request(query, params):
    """Assemble a Bing-Web request."""

    engine_region = traits.get_region(params['searxng_locale'], 'en-US')
    engine_language = traits.get_language(params['searxng_locale'], 'en')

    SID = uuid.uuid1().hex.upper()
    CVID = uuid.uuid1().hex.upper()

    set_bing_cookies(params, engine_language, engine_region, SID)

    # build URL query
    # ---------------

    # query term
    page = int(params.get('pageno', 1))
    query_params = {
        # fmt: off
        'q': query,
        'pq': query,
        'cvid': CVID,
        'qs': 'n',
        'sp': '-1'
        # fmt: on
    }

    # page
    if page > 1:
        referer = base_url + '?' + urlencode(query_params)
        params['headers']['Referer'] = referer
        logger.debug("headers.Referer --> %s", referer)

    query_params['first'] = _get_offset_from_pageno(page)

    if page == 2:
        query_params['FORM'] = 'PERE'
    elif page > 2:
        query_params['FORM'] = 'PERE%s' % (page - 2)

    filters = ''
    if params['time_range']:
        query_params['filt'] = 'custom'

        if params['time_range'] == 'day':
            filters = 'ex1:"ez1"'
        elif params['time_range'] == 'week':
            filters = 'ex1:"ez2"'
        elif params['time_range'] == 'month':
            filters = 'ex1:"ez3"'
        elif params['time_range'] == 'year':
            epoch_1970 = datetime.date(1970, 1, 1)
            today_no = (datetime.date.today() - epoch_1970).days
            filters = 'ex1:"ez5_%s_%s"' % (today_no - 365, today_no)

    params['url'] = base_url + '?' + urlencode(query_params)
    if filters:
        params['url'] = params['url'] + '&filters=' + filters
    return params


def response(resp):

    results = []
    result_len = 0

    dom = html.fromstring(resp.text)

    # parse results again if nothing is found yet

    url_to_resolve = []
    url_to_resolve_index = []
    for i, result in enumerate(eval_xpath_list(dom, '//li[@class="b_algo"]')):

        link = eval_xpath(result, './/h2/a')[0]
        url = link.attrib.get('href')
        title = extract_text(link)
        content = extract_text(eval_xpath(result, './/p'))

        # get the real URL either using the URL shown to user or following the Bing URL
        if url.startswith('https://www.bing.com/ck/a?'):
            url_cite = extract_text(eval_xpath(result, './/div[@class="b_attribution"]/cite'))
            # Bing can shorten the URL either at the end or in the middle of the string
            if (
                url_cite
                and url_cite.startswith('https://')
                and '…' not in url_cite
                and '...' not in url_cite
                and '›' not in url_cite
            ):
                # no need for an additional HTTP request
                url = url_cite
            else:
                # resolve the URL with an additional HTTP request
                url_to_resolve.append(url.replace('&ntb=1', '&ntb=F'))
                url_to_resolve_index.append(i)
                url = None  # remove the result if the HTTP Bing redirect raise an exception

        # append result
        results.append({'url': url, 'title': title, 'content': content})

    # resolve all Bing redirections in parallel
    request_list = [
        network.Request.get(u, allow_redirects=False, headers=resp.search_params['headers']) for u in url_to_resolve
    ]
    response_list = network.multi_requests(request_list)
    for i, redirect_response in enumerate(response_list):
        if not isinstance(redirect_response, Exception):
            results[url_to_resolve_index[i]]['url'] = redirect_response.headers['location']

    # get number_of_results
    try:
        result_len_container = "".join(eval_xpath(dom, '//span[@class="sb_count"]//text()'))
        if "-" in result_len_container:

            # Remove the part "from-to" for paginated request ...
            result_len_container = result_len_container[result_len_container.find("-") * 2 + 2 :]

        result_len_container = re.sub('[^0-9]', '', result_len_container)

        if len(result_len_container) > 0:
            result_len = int(result_len_container)

    except Exception as e:  # pylint: disable=broad-except
        logger.debug('result error :\n%s', e)

    if result_len and _get_offset_from_pageno(resp.search_params.get("pageno", 0)) > result_len:
        return []

    results.append({'number_of_results': result_len})
    return results


def fetch_traits(engine_traits: EngineTraits):
    """Fetch languages and regions from Bing-Web."""

    xpath_market_codes = '//table[1]/tbody/tr/td[3]'
    # xpath_country_codes = '//table[2]/tbody/tr/td[2]'
    xpath_language_codes = '//table[3]/tbody/tr/td[2]'

    _fetch_traits(engine_traits, bing_traits_url, xpath_language_codes, xpath_market_codes)


def _fetch_traits(engine_traits: EngineTraits, url: str, xpath_language_codes: str, xpath_market_codes: str):

    # insert alias to map from a language (zh) to a language + script (zh_Hans)
    engine_traits.languages['zh'] = 'zh-hans'

    resp = network.get(url)

    if not resp.ok:
        print("ERROR: response from peertube is not OK.")

    dom = html.fromstring(resp.text)

    map_lang = {'jp': 'ja'}
    for td in eval_xpath(dom, xpath_language_codes):
        eng_lang = td.text

        if eng_lang in ('en-gb', 'pt-br'):
            # language 'en' is already in the list and a language 'en-gb' can't
            # be handled in SearXNG, same with pt-br which is covered by pt-pt.
            continue

        babel_lang = map_lang.get(eng_lang, eng_lang).replace('-', '_')
        try:
            sxng_tag = language_tag(babel.Locale.parse(babel_lang))
        except babel.UnknownLocaleError:
            print("ERROR: language (%s) is unknown by babel" % (eng_lang))
            continue
        conflict = engine_traits.languages.get(sxng_tag)
        if conflict:
            if conflict != eng_lang:
                print("CONFLICT: babel %s --> %s, %s" % (sxng_tag, conflict, eng_lang))
            continue
        engine_traits.languages[sxng_tag] = eng_lang

    map_region = {
        'en-ID': 'id_ID',
        'no-NO': 'nb_NO',
    }

    for td in eval_xpath(dom, xpath_market_codes):
        eng_region = td.text
        babel_region = map_region.get(eng_region, eng_region).replace('-', '_')

        if eng_region == 'en-WW':
            engine_traits.all_locale = eng_region
            continue

        try:
            sxng_tag = region_tag(babel.Locale.parse(babel_region))
        except babel.UnknownLocaleError:
            print("ERROR: region (%s) is unknown by babel" % (eng_region))
            continue
        conflict = engine_traits.regions.get(sxng_tag)
        if conflict:
            if conflict != eng_region:
                print("CONFLICT: babel %s --> %s, %s" % (sxng_tag, conflict, eng_region))
            continue
        engine_traits.regions[sxng_tag] = eng_region
