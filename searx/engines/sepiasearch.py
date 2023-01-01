# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""
SepiaSearch (Videos)
~~~~~~~~~~~~~~~~~~~~

Sepiasearch uses the same languages as :py:obj:`searx.engines.peertube`
"""

from typing import TYPE_CHECKING

from json import loads
from urllib.parse import urlencode
from datetime import datetime
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta

from searx.engines.peertube import fetch_traits  # pylint: disable=unused-import
from searx.enginelib.traits import EngineTraits

if TYPE_CHECKING:
    import logging

    logger: logging.Logger

traits: EngineTraits

about = {
    # pylint: disable=line-too-long
    "website": 'https://sepiasearch.org',
    "wikidata_id": None,
    "official_api_documentation": "https://framagit.org/framasoft/peertube/search-index/-/tree/master/server/controllers/api",
    "use_official_api": True,
    "require_api_key": False,
    "results": 'JSON',
}

# engine dependent config
categories = ['videos']
paging = True

base_url = 'https://sepiasearch.org/api/v1/search/videos'

time_range_support = True
time_range_table = {
    'day': relativedelta(),
    'week': relativedelta(weeks=-1),
    'month': relativedelta(months=-1),
    'year': relativedelta(years=-1),
}

safesearch = True
safesearch_table = {0: 'both', 1: 'false', 2: 'false'}


def minute_to_hm(minute):
    if isinstance(minute, int):
        return "%d:%02d" % (divmod(minute, 60))
    return None


def request(query, params):

    # eng_region = traits.get_region(params['searxng_locale'], 'en_US')
    eng_lang = traits.get_language(params['searxng_locale'], None)

    params['url'] = (
        base_url
        + '?'
        + urlencode(
            {
                'search': query,
                'start': (params['pageno'] - 1) * 10,
                'count': 10,
                # -createdAt: sort by date ascending / createdAt: date descending
                'sort': '-match',  # sort by *match descending*
                'nsfw': safesearch_table[params['safesearch']],
            }
        )
    )

    if eng_lang is not None:
        params['url'] += '&languageOneOf[]=' + eng_lang
        params['url'] += '&boostLanguages[]=' + eng_lang

    if params['time_range'] in time_range_table:
        time = datetime.now().date() + time_range_table[params['time_range']]
        params['url'] += '&startDate=' + time.isoformat()

    return params


def response(resp):
    results = []

    search_results = loads(resp.text)

    if 'data' not in search_results:
        return []

    for result in search_results['data']:
        metadata = [
            x
            for x in [
                result.get('channel', {}).get('displayName'),
                result.get('channel', {}).get('host'),
                ', '.join(result.get('tags', [])),
            ]
            if x
        ]

        results.append(
            {
                'url': result['url'],
                'title': result['name'],
                'content': result.get('description') or '',
                'author': result.get('account', {}).get('displayName'),
                'length': minute_to_hm(result.get('duration')),
                'template': 'videos.html',
                'publishedDate': parse(result['publishedAt']),
                'iframe_src': result.get('embedUrl'),
                'thumbnail': result.get('thumbnailUrl') or result.get('previewUrl'),
                'metadata': ' | '.join(metadata),
            }
        )

    return results
