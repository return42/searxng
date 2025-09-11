# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Astrophysics Data System (ADS_) is a digital library portal for
researchers in astronomy and physics, operated by the Smithsonian Astrophysical
Observatory (SAO) under a NASA grant.  The ADS_ is a solr instance, but not with
the standard API paths.

.. note::

   The ADS_ engine requires an :py:obj:`API key <api_key>`.

.. _ADS: https://ui.adsabs.harvard.edu

Configuration
=============

The engine has the following additional settings:

- :py:obj:`api_key`
- :py:obj:`ads_sort`

.. code:: yaml

  - name: astrophysics data system
    api_key: "..."


Implementations
===============

"""

import typing as t

from datetime import datetime
from json import loads
from urllib.parse import urlencode
from searx.exceptions import SearxEngineAPIException

about = {
    "website": "https://ui.adsabs.harvard.edu/",
    "wikidata_id": "Q752099",
    "official_api_documentation": "https://ui.adsabs.harvard.edu/help/api/api-docs.html",
    "use_official_api": True,
    "require_api_key": True,
    "results": "JSON",
}

base_url = "https://api.adsabs.harvard.edu/v1/search"
result_base_url = "https://ui.adsabs.harvard.edu/abs/"
categories = ["science", "scientific publications"]
rows = 10
paging = True

ads_sort = "asc"  # sorting: asc or desc
"""..."""  # FIXME: doc

ads_field_list = ["bibcode", "author", "title", "abstract", "doi", "date"]  # list of field names to display on the UI
"""..."""  # FIXME: doc

ads_default_fields = ""  # default field to query
"""..."""  # FIXME: doc

ads_query_fields = ""  # query fields
"""..."""  # FIXME: doc

api_key = "unset"
"""..."""  # FIXME: doc


def init(engine_settings: dict[str, t.Any]) -> bool:
    """Initialization of the ADS_ engine, checks whether the :py:obj:`api_key`
    is set, otherwise the engine is inactive.
    """
    raise Exception("fff")
    import time

    time.sleep(50)
    key: str = engine_settings.get("api_key", "")
    if key and key not in ("unset", "unknown", "..."):
        return True
    logger.error("Astrophysics Data System (ADS) API key is not set or invalid.")
    return False


def request(query: str, params: dict[str, t.Any]) -> None:
    args: dict[str, str | int] = {
        "q": query,
        "rows": rows,
        "fl": ",".join(field_list),
        "start": rows * (params["pageno"] - 1),
    }
    if query_fields:
        args["qf"] = ",".join(query_fields)
    if default_fields:
        args["df"] = default_fields
    if ads_sort:
        args["sort"] = ads_sort

    params["headers"]["Authorization"] = f"Bearer {api_key}"
    params["url"] = f"{base_url}/query?{urlencode(args)}"


def response(resp):
    try:
        resp_json = loads(resp.text)
    except Exception as e:
        raise SearxEngineAPIException("failed to parse response") from e

    if "error" in resp_json:
        raise SearxEngineAPIException(resp_json["error"]["msg"])

    resp_json = resp_json["response"]
    result_len = resp_json["numFound"]
    results = []

    for res in resp_json["docs"]:
        author = res.get("author")

        if author:
            author = author[0] + " et al."

        results.append(
            {
                "url": result_base_url + res.get("bibcode") + "/",
                "title": res.get("title")[0],
                "author": author,
                "content": res.get("abstract"),
                "doi": res.get("doi"),
                "publishedDate": datetime.fromisoformat(res.get("date")),
            }
        )

    results.append({"number_of_results": result_len})

    return results
