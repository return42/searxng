# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""peertube (videos)
"""

from json import loads
from datetime import datetime
from urllib.parse import urlencode
from searx.utils import html_to_text

from searx.enginelib.traits import EngineTraits

traits: EngineTraits

# about
about = {
    "website": 'https://joinpeertube.org',
    "wikidata_id": 'Q50938515',
    "official_api_documentation": 'https://docs.joinpeertube.org/api-rest-reference.html',
    "use_official_api": True,
    "require_api_key": False,
    "results": 'JSON',
}

# engine dependent config
categories = ["videos"]
paging = True
base_url = "https://peer.tube"

# do search-request
def request(query, params):
    """Build peertube request"""
    search_url = base_url.rstrip("/") + "/api/v1/search/videos/?pageno={pageno}&{query}"
    query_dict = {"search": query}

    pageno = (params["pageno"] - 1) * 15
    engine_lang = traits.get_language(params["searxng_locale"])
    if engine_lang:
        query_dict["languageOneOf"] = engine_lang

    params["url"] = search_url.format(query=urlencode(query_dict), pageno=pageno)
    return params


# get response from search-request
def response(resp):
    sanitized_url = base_url.rstrip("/")
    results = []

    search_res = loads(resp.text)

    # return empty array if there are no results
    if "data" not in search_res:
        return []

    # parse results
    for res in search_res["data"]:
        title = res["name"]
        url = sanitized_url + "/videos/watch/" + res["uuid"]
        description = res["description"]
        if description:
            content = html_to_text(res["description"])
        else:
            content = ""
        thumbnail = sanitized_url + res["thumbnailPath"]
        publishedDate = datetime.strptime(res["publishedAt"], "%Y-%m-%dT%H:%M:%S.%fZ")

        results.append(
            {
                "template": "videos.html",
                "url": url,
                "title": title,
                "content": content,
                "publishedDate": publishedDate,
                "iframe_src": sanitized_url + res["embedPath"],
                "thumbnail": thumbnail,
            }
        )

    # return results
    return results


def fetch_traits(engine_traits: EngineTraits):
    """Fetch languages from peertube."""

    # pylint: disable=import-outside-toplevel
    import re
    import babel
    from searx.locales import language_tag
    from searx import network

    resp = network.get('https://framagit.org/framasoft/peertube/search-index/-/raw/master/client/src/views/Search.vue')

    if not resp.ok:
        print("ERROR: response from peertube is not OK.")
        return

    js_lang = re.search(r"videoLanguages \(\)[^\n]+(.*?)\]", resp.text, re.DOTALL)
    if not js_lang:
        print("ERROR: can't determine languages from peertube")
        return

    for lang in re.finditer(r"\{ id: '([a-z]+)', label:", js_lang.group(1)):
        try:
            eng_tag = lang.group(1)
            if eng_tag == 'oc':
                # Occitanis not known by babel, its closest relative is Catalan
                # but 'ca' is already in the list of engine_traits.languages -->
                # 'oc' will be ignored.
                continue

            sxng_tag = language_tag(babel.Locale.parse(eng_tag))

        except babel.UnknownLocaleError:
            print("ERROR: %s is unknown by babel" % eng_tag)
            continue

        conflict = engine_traits.languages.get(sxng_tag)
        if conflict:
            if conflict != eng_tag:
                print("CONFLICT: babel %s --> %s, %s" % (sxng_tag, conflict, eng_tag))
            continue
        engine_traits.languages[sxng_tag] = eng_tag
