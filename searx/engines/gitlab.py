# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gitlab (IT)

"""

from urllib.parse import urlencode
from dateutil import parser

about = {
    "website": 'https://gitlab.com/',
    "wikidata_id": "Q16639197",
    "official_api_documentation": "https://docs.gitlab.com/ee/api/",
    "use_official_api": False,
    "require_api_key": False,
    "results": "JSON",
}

categories = ['it', 'repos']
paging = True

base_url = "https://gitlab.com"


def request(query, params):
    args = {'search': query, 'page': params['pageno']}
    params['url'] = f"{base_url}/api/v4/projects?{urlencode(args)}"

    return params


def response(resp):
    results = []

    for item in resp.json():
        results.append(
            {
                'template': 'packages.html',
                'url': item.get('web_url'),
                'title': item.get('name'),
                'content': item.get('description'),
                'thumbnail': item.get('avatar_url'),
                'package_name': item.get('name'),
                'maintainer': item.get('namespace', {}).get('name'),
                'publishedDate': parser.parse(item.get('last_activity_at') or item.get("created_at")),
                'tags': item.get('tag_list', []),
                'popularity': item.get('star_count'),
                'homepage': item.get('readme_url'),
                'source_code_url': item.get('http_url_to_repo'),
            }
        )

    return results
