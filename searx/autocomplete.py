# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""This module implements functions needed for the autocompleter.

"""
# pylint: disable=use-dict-literal

from json import loads
from urllib.parse import urlencode

from lxml import etree
from httpx import HTTPError

from searx import settings
from searx.engines import engines
from searx.network import get as http_get
from searx.exceptions import SearxEngineResponseException

# a fetch_supported_languages() for XPath engines isn't available right now
# _brave = ENGINES_LANGUAGES['brave'].keys()


def get(*args, **kwargs):
    if 'timeout' not in kwargs:
        kwargs['timeout'] = settings['outgoing']['request_timeout']
    kwargs['raise_for_httperror'] = True
    return http_get(*args, **kwargs)


def brave(query, _lang):
    # brave search autocompleter
    url = 'https://search.brave.com/api/suggest?'
    url += urlencode({'q': query})
    country = 'all'
    # if lang in _brave:
    #    country = lang
    kwargs = {'cookies': {'country': country}}
    resp = get(url, **kwargs)

    results = []

    if resp.ok:
        data = resp.json()
        for item in data[1]:
            results.append(item)
    return results


def dbpedia(query, _lang):
    # dbpedia autocompleter, no HTTPS
    autocomplete_url = 'https://lookup.dbpedia.org/api/search.asmx/KeywordSearch?'

    response = get(autocomplete_url + urlencode(dict(QueryString=query)))

    results = []

    if response.ok:
        dom = etree.fromstring(response.content)
        results = dom.xpath('//Result/Label//text()')

    return results


def duckduckgo(query, _lang):
    # duckduckgo autocompleter
    url = 'https://ac.duckduckgo.com/ac/?{0}&type=list'

    resp = loads(get(url.format(urlencode(dict(q=query)))).text)
    if len(resp) > 1:
        return resp[1]
    return []


def google(query, lang):
    # google autocompleter
    autocomplete_url = 'https://suggestqueries.google.com/complete/search?client=toolbar&'

    response = get(autocomplete_url + urlencode(dict(hl=lang, q=query)))

    results = []

    if response.ok:
        dom = etree.fromstring(response.text)
        results = dom.xpath('//suggestion/@data')

    return results


def seznam(query, _lang):
    # seznam search autocompleter
    url = 'https://suggest.seznam.cz/fulltext/cs?{query}'

    resp = get(
        url.format(
            query=urlencode(
                {'phrase': query, 'cursorPosition': len(query), 'format': 'json-2', 'highlight': '1', 'count': '6'}
            )
        )
    )

    if not resp.ok:
        return []

    data = resp.json()
    return [
        ''.join([part.get('text', '') for part in item.get('text', [])])
        for item in data.get('result', [])
        if item.get('itemType', None) == 'ItemType.TEXT'
    ]


def startpage(query, lang):
    # startpage autocompleter
    lui = engines['startpage'].supported_languages.get(lang, 'english')  # vintage / deprecated
    url = 'https://startpage.com/suggestions?{query}'
    resp = get(url.format(query=urlencode({'q': query, 'segment': 'startpage.udog', 'lui': lui})))
    data = resp.json()
    return [e['text'] for e in data.get('suggestions', []) if 'text' in e]


def swisscows(query, _lang):
    # swisscows autocompleter
    url = 'https://swisscows.ch/api/suggest?{query}&itemsCount=5'

    resp = loads(get(url.format(query=urlencode({'query': query}))).text)
    return resp


def qwant(query, sxng_locale):
    """Autocomplete from Qwant. Supports Qwant's regions."""
    results = []

    locale = engines['startpage'].traits.get_region(sxng_locale, 'en_US')
    url = 'https://api.qwant.com/v3/suggest?{query}'
    resp = get(url.format(query=urlencode({'q': query, 'locale': locale, 'version': '2'})))

    if resp.ok:
        data = resp.json()
        if data['status'] == 'success':
            for item in data['data']['items']:
                results.append(item['value'])

    return results


def wikipedia(query, sxng_locale):
    """Autocomplete from Wikipedia. Supports Wikipedia's languages (aka netloc)."""
    results = []
    eng_traits = engines['wikipedia'].traits
    wiki_lang = eng_traits.get_language(sxng_locale, 'en')
    wiki_netloc = eng_traits.custom['wiki_netloc'].get(wiki_lang, 'en.wikipedia.org')

    url = 'https://{wiki_netloc}/w/api.php?{args}'
    args = urlencode(
        {
            'action': 'opensearch',
            'format': 'json',
            'formatversion': '2',
            'search': query,
            'namespace': '0',
            'limit': '10',
        }
    )
    resp = get(url.format(args=args, wiki_netloc=wiki_netloc))
    if resp.ok:
        data = resp.json()
        if len(data) > 1:
            results = data[1]

    return results


def yandex(query, _lang):
    # yandex autocompleter
    url = "https://suggest.yandex.com/suggest-ff.cgi?{0}"

    resp = loads(get(url.format(urlencode(dict(part=query)))).text)
    if len(resp) > 1:
        return resp[1]
    return []


backends = {
    'dbpedia': dbpedia,
    'duckduckgo': duckduckgo,
    'google': google,
    'seznam': seznam,
    'startpage': startpage,
    'swisscows': swisscows,
    'qwant': qwant,
    'wikipedia': wikipedia,
    'brave': brave,
    'yandex': yandex,
}


def search_autocomplete(backend_name, query, sxng_locale):
    backend = backends.get(backend_name)
    if backend is None:
        return []

    if engines[backend_name].traits.data_type != "traits_v1":
        # vintage / deprecated
        if not sxng_locale or sxng_locale == 'all':
            sxng_locale = 'en'
        else:
            sxng_locale = sxng_locale.split('-')[0]

    try:
        return backend(query, sxng_locale)
    except (HTTPError, SearxEngineResponseException):
        return []
