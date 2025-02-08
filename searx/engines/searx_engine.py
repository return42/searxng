# SPDX-License-Identifier: AGPL-3.0-or-later
"""SearXNG search API"""

# about
about = {
    "website": 'https://github.com/searxng/searxng',
    "wikidata_id": 'Q17639196',
    "official_api_documentation": 'https://docs.searxng.org/dev/search_api.html',
    "use_official_api": True,
    "require_api_key": False,
    "results": 'JSON',
}

sxng_categories = ["global"]
sxng_engines = []

# search-url
instance_urls = []
instance_index = 0


def request(query, params):
    global instance_index  # pylint: disable=global-statement
    params['url'] = instance_urls[instance_index % len(instance_urls)]
    params['method'] = 'POST'

    instance_index += 1

    params['data'] = {
        'q': query,
        'pageno': params['pageno'],
        'language': params['language'],
        'time_range': params['time_range'],
        'format': 'json',
    }
    if sxng_categories:
        params["data"]["categories"] =  ",".join(sxng_categories),
    if sxng_engines:
        params["data"]["engines"] =  ",".join(sxng_engines),

    return params


def response(resp):

    response_json = resp.json()
    results = response_json['results']

    for i in ('answers', 'infoboxes'):
        results.extend(response_json[i])

    results.extend({'suggestion': s} for s in response_json['suggestions'])
    results.append({'number_of_results': response_json['number_of_results']})

    return results
