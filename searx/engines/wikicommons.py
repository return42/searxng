# SPDX-License-Identifier: AGPL-3.0-or-later
"""`Wikimedia Commons`_ is a collection of more than 120 millions freely usable
media files to which anyone can contribute.

This engine uses the `MediaWiki query API`_, with which engines can be configured
for searching images, videos, audio, and other files in the Wikimedia.

.. _MediaWiki query API: https://commons.wikimedia.org/w/api.php?action=help&modules=query
.. _Wikimedia Commons: https://commons.wikimedia.org/


Configuration
=============

The engine has the following additional settings:

.. code:: yaml

   - name: wikicommons.images
     engine: wikicommons
     wc_search_type: image

   - name: wikicommons.videos
     engine: wikicommons
     wc_search_type: video

   - name: wikicommons.audio
     engine: wikicommons
     wc_search_type: audio

   - name: wikicommons.files
     engine: wikicommons
     wc_search_type: file


Implementations
===============

en.


"""

import typing as t
import datetime
from urllib.parse import urlencode

from searx.utils import html_to_text, humanize_bytes
from searx.result_types import EngineResults

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

about = {
    "website": "https://commons.wikimedia.org/",
    "wikidata_id": "Q565",
    "official_api_documentation": "https://commons.wikimedia.org/w/api.php",
    "use_official_api": True,
    "require_api_key": False,
    "results": "JSON",
}

categories: list[str] = []
paging = True
number_of_results = 10

wc_api_url = "https://commons.wikimedia.org/w/api.php"
wc_search_type: str = ""

SEARCH_TYPES: dict[str, str] = {
    "image": "bitmap|drawing",
    "video": "video",
    "audio": "audio",
    "file": "multimedia|office|archive|3d",
}
# FileType = t.Literal["bitmap", "drawing", "video", "audio", "multimedia", "office", "archive", "3d"]
# FILE_TYPES = list(t.get_args(FileType))


def setup(engine_settings: dict[str, t.Any]) -> bool:
    """Initialization of the Wikimedia engine, checks if the value configured in
    :py:obj:`wc_search_type` is valid."""

    if engine_settings.get("wc_file_types") not in SEARCH_TYPES:
        logger.error(
            "wc_file_types: %s isn't a valid file type (%s)",
            engine_settings.get("wc_file_types"),
            ",".join(SEARCH_TYPES.keys()),
        )
        return False
    return True


def request(query: str, params: "OnlineParams") -> None:
    uselang: str = "en"
    if params["searxng_locale"] != "all":
        uselang = params["searxng_locale"].split("-")[0]
    filetype = SEARCH_TYPES[wc_search_type]
    args = {
        # https://commons.wikimedia.org/w/api.php
        "format": "json",
        "uselang": uselang,
        "action": "query",
        # https://commons.wikimedia.org/w/api.php?action=help&modules=query
        "prop": "info|imageinfo",
        # generator (gsr optins) https://commons.wikimedia.org/w/api.php?action=help&modules=query%2Bsearch
        "generator": "search",
        "gsrnamespace": "6",  # https://www.mediawiki.org/wiki/Help:Namespaces#Renaming_namespaces
        "gsrprop": "snippet",
        "gsrlimit": number_of_results,
        "gsroffset": number_of_results * (params["pageno"] - 1),
        "gsrsearch": f"filetype:{filetype} {query}",
        # imageinfo: https://commons.wikimedia.org/w/api.php?action=help&modules=query%2Bimageinfo
        "iiprop": "url|size|mime",
        "iiurlheight": "180",  # needed for the thumb url
    }
    params["url"] = f"{wc_api_url}?{urlencode(args, safe=':|')}"


def response(resp: "SXNG_Response") -> EngineResults:

    res = EngineResults()
    json_data = resp.json()
    pages = json_data.get("queryx", {}).get("pages", {}).values()

    def _str(k: str) -> str:
        return item.get(k, "")

    for item in pages:

        imageinfo = item["imageinfo"][0]

        title = _str("title").replace("File:", "").rsplit(".", 1)[0]
        url = _str("descriptionurl")
        content = html_to_text(_str("snippet"))
        thumbnail = _str("thumburl")

        size = imageinfo.get("size")
        if size:
            size = humanize_bytes(size)
        duration = imageinfo.get("duration")
        if duration:
            duration = datetime.timedelta(seconds=int(duration))

        mtype = subtype = _str("mime")
        if mtype:
            mtype, subtype = mtype.split("/", 1)[0]

        if wc_search_type == "file":
            res.add(
                res.types.File(
                    title=title,
                    url=url,
                    content=content,
                    size=size,
                    mtype=mtype,
                    subtype=subtype,
                    embedded=_str("url"),
                )
            )
            continue

        if wc_search_type == "image":
            res.add(
                res.types.LegacyResult(
                    template="images.html",
                    title=title,
                    url=url,
                    content=content,
                    img_src=_str("url"),
                    thumbnail_src=thumbnail,
                    resolution=_str("width") + " x " + _str("height"),
                    img_format=_str("mime"),
                    filesize=size,
                )
            )
            continue

        if wc_search_type == "video":
            res.add(
                res.types.LegacyResult(
                    template="videos.html",
                    title=title,
                    url=url,
                    content=content,
                    iframe_src=_str("url"),
                    length=duration,
                )
            )
            continue

        if wc_search_type == "audio":
            res.add(
                res.types.MainResult(
                    template="audio.html",
                    title=title,
                    url=url,
                    content=content,
                    audio_src=_str("url"),
                    length=duration,
                )
            )
            continue

    return res
