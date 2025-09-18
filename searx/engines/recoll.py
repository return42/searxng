# SPDX-License-Identifier: AGPL-3.0-or-later
""".. sidebar:: info

   - `Recoll <https://www.lesbonscomptes.com/recoll/>`_
   - `recoll-webui <https://framagit.org/medoc92/recollwebui.git>`_
   - :origin:`searx/engines/recoll.py`

Recoll_ is a desktop full-text search tool based on Xapian.  By itself Recoll_
does not offer WEB or API access, this can be achieved using recoll-webui_

Configuration
=============

You must configure the following settings:

- :py:obj:`base_url`
- :py:obj:`mount_prefix`
- :py:obj:`dl_prefix`
- :py:obj:`search_dir`

Example scenario:

#. Recoll indexes a local filesystem mounted in ``/export/documents/reference``,
#. the Recoll search interface can be reached at https://recoll.example.org/ and
#. the contents of this filesystem can be reached though https://download.example.org/reference

.. code:: yaml

   base_url: https://recoll.example.org
   mount_prefix: /export/documents
   dl_prefix: https://download.example.org
   search_dir: ""

Implementations
===============

"""
import typing as t

from datetime import date, timedelta, datetime
from urllib.parse import urlencode, quote

from searx.result_types import EngineResults
from searx.utils import html_to_text, humanize_bytes

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams


about = {
    "website": None,
    "wikidata_id": "Q15735774",
    "official_api_documentation": "https://www.lesbonscomptes.com/recoll/",
    "use_official_api": True,
    "require_api_key": False,
    "results": "JSON",
}

paging = True
time_range_support = True

base_url: str = ""
"""Location where recoll-webui can be reached."""

mount_prefix: str = ""
"""Location where the file hierarchy is mounted on your *local* filesystem."""

dl_prefix: str = ""
"""Location where the file hierarchy as indexed by recoll can be reached."""

search_dir: str = ""
"""Part of the indexed file hierarchy to be search, if empty the full domain is
searched."""

_s2i: dict[str | None, int] = {"day": 1, "week": 7, "month": 30, "year": 365}

def setup(engine_settings: dict[str, t.Any]) -> bool:
    """Initialization of the Recoll engine, checks if the mandatory values are
    configured.
    """
    missing: list[str] = []
    for cfg_name in ["base_url", "mount_prefix", "dl_prefix"]:
        if not engine_settings.get(cfg_name):
            missing.append(cfg_name)
    if missing:
        logger.error("missing recoll configuration: %s", missing)
        return False

    if engine_settings["base_url"].endswith("/"):
        engine_settings["base_url"] = engine_settings["base_url"][:-1]
    return True


def search_after(time_range: str|None) -> str:
    offset = _s2i.get(time_range, 0)
    if not offset:
        return ""
    return (date.today() - timedelta(days=offset)).isoformat()


def request(query: str, params: "OnlineParams") -> None:
    args = {
        "query": query,
        "page": params["pageno"],
        "after": search_after(params["time_range"]),
        "dir": search_dir,
        "highlight": 0,
    }
    params["url"] = f"{base_url}/json?{urlencode(args)}"




embedded_url = '<{ttype} controls height="166px" ' + 'src="{url}" type="{mtype}"></{ttype}>'




def response(resp: "SXNG_Response") -> EngineResults:
    res = EngineResults()
    json_data = resp.json()

    if not json_data:
        return res

    def _str(k: str) -> str:
        return result.get(k, "")

    for result in json_data.get("results", []):

        url = _str("url").replace('file://' + mount_prefix, dl_prefix),
        mtype = subtype = _str("mime")
        if mtype:
            mtype, subtype = (mtype.split("/", 1) + [""])[:2]
        embedded = ""
        if mtype in ["audio", "video"]:
            embedded = embedded_url.format(
                ttype=mtype, url=quote(url.encode('utf8'), '/:'), mtype=result['mtype']
                )

        res.add(
            res.types.File(
                title = _str("label"),
                url =url,
                content = _str("snippet"),
                size=_str("size"),
                filename=_str("filename"),
                abstract=_str("abstract"),
                author=_str("author"),
                mtype=mtype,
                subtype=subtype,
                time=_str("time"),

            )
        )


        XXXXXXXXXXXXXXXX

    for result in response_json.get('results', []):
        title = result['label']
        url = result['url'].replace('file://' + mount_prefix, dl_prefix)
        content = '{}'.format(result['snippet'])

        # append result
        item = {'url': url, 'title': title, 'content': content, 'template': 'files.html'}

        if result['size']:
            item['size'] = int(result['size'])

        for parameter in ['filename', 'abstract', 'author', 'mtype', 'time']:
            if result[parameter]:
                item[parameter] = result[parameter]

        # facilitate preview support for known mime types
        if 'mtype' in result and '/' in result['mtype']:
            (mtype, subtype) = result['mtype'].split('/')
            item['mtype'] = mtype
            item['subtype'] = subtype

            if mtype in ['audio', 'video']:
                item['embedded'] = embedded_url.format(
                    ttype=mtype, url=quote(url.encode('utf8'), '/:'), mtype=result['mtype']
                )

            if mtype in ['image'] and subtype in ['bmp', 'gif', 'jpeg', 'png']:
                item['thumbnail'] = url

        results.append(item)

    if 'nres' in response_json:
        results.append({'number_of_results': response_json['nres']})

    return results
