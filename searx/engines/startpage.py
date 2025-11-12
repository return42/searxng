# SPDX-License-Identifier: AGPL-3.0-or-later
"""Startpage's language & region selectors are a mess ..

.. _startpage regions:

Startpage regions
=================

In the list of regions there are tags we need to map to common region tags::

  pt-BR_BR --> pt_BR
  zh-CN_CN --> zh_Hans_CN
  zh-TW_TW --> zh_Hant_TW
  zh-TW_HK --> zh_Hant_HK
  en-GB_GB --> en_GB

and there is at least one tag with a three letter language tag (ISO 639-2)::

  fil_PH --> fil_PH

The locale code ``no_NO`` from Startpage does not exists and is mapped to
``nb-NO``::

    babel.core.UnknownLocaleError: unknown locale 'no_NO'

For reference see languages-subtag at iana; ``no`` is the macrolanguage [1]_ and
W3C recommends subtag over macrolanguage [2]_.

.. [1] `iana: language-subtag-registry
   <https://www.iana.org/assignments/language-subtag-registry/language-subtag-registry>`_ ::

      type: language
      Subtag: nb
      Description: Norwegian Bokmål
      Added: 2005-10-16
      Suppress-Script: Latn
      Macrolanguage: no

.. [2]
   Use macrolanguages with care.  Some language subtags have a Scope field set to
   macrolanguage, i.e. this primary language subtag encompasses a number of more
   specific primary language subtags in the registry.  ...  As we recommended for
   the collection subtags mentioned above, in most cases you should try to use
   the more specific subtags ... `W3: The primary language subtag
   <https://www.w3.org/International/questions/qa-choosing-language-tags#langsubtag>`_

.. _startpage languages:

Startpage languages
===================

:py:obj:`send_accept_language_header`:
  The displayed name in Startpage's settings page depend on the location of the
  IP when ``Accept-Language`` HTTP header is unset.  In :py:obj:`fetch_traits`
  we use::

    'Accept-Language': "en-US,en;q=0.5",
    ..

  to get uniform names independent from the IP).

.. _startpage categories:

Startpage categories
====================

Startpage's category (for Web-search, News, Videos, ..) is set by
:py:obj:`startpage_categ` in  settings.yml::

  - name: startpage
    engine: startpage
    startpage_categ: web
    ...

.. hint::

  Supported categories are ``web``, ``news`` and ``images``.

"""
# pylint: disable=too-many-statements

import typing as t

from collections import OrderedDict
from collections import abc
import re
from unicodedata import normalize, combining
from datetime import datetime, timedelta
from json import loads

import dateutil.parser
import lxml.html
import babel.localedata

from searx.utils import extr, extract_text, gen_useragent, html_to_text, humanize_bytes, remove_pua_from_str
from searx.network import get  # see https://github.com/searxng/searxng/issues/762
from searx.exceptions import SearxEngineCaptchaException
from searx.locales import region_tag
from searx.enginelib.traits import EngineTraits
from searx.result_types import EngineResults, MainResult, LegacyResult
from searx import sidecar

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams
    from searx.sidecar_pkg.types import SessionType


# about
about = {
    "website": "https://startpage.com",
    "wikidata_id": "Q2333295",
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
}

startpage_categ = "web"
"""Startpage's category, visit :ref:`startpage categories`.
"""

send_accept_language_header = True
"""Startpage tries to guess user's language and territory from the HTTP
``Accept-Language``.  Optional the user can select a search-language (can be
different to the UI language) and a region filter.
"""

# engine dependent config
categories = ["general", "web"]
paging = True
max_page = 18
"""Tested 18 pages maximum (argument ``page``), to be save max is set to 20."""

time_range_support = True
safesearch = True

time_range_dict = {"day": "d", "week": "w", "month": "m", "year": "y"}
safesearch_dict = {0: "1", 1: "0", 2: "0"}

# search-url
base_url = "https://www.startpage.com"
search_url = base_url + "/sp/search"

# specific xpath variables
# ads xpath //div[@id="results"]/div[@id="sponsored"]//div[@class="result"]
# not ads: div[@class="result"] are the direct children of div[@id="results"]
search_form_xpath = '//form[@id="search"]'
"""XPath of Startpage's origin search form

.. code: html

    <form action="/sp/search" method="post">
      <input type="text" name="query"  value="" ..>
      <input type="hidden" name="t" value="device">
      <input type="hidden" name="lui" value="english">
      <input type="hidden" name="sc" value="Q7Mt5TRqowKB00">
      <input type="hidden" name="cat" value="web">
      <input type="hidden" class="abp" id="abp-input" name="abp" value="1">
    </form>
"""

session_type: "SessionType" = "startpage.com"
"""Type of the WEB session / see :py:obj:`searx.sidecar`."""


def request(query: str, params: "OnlineParams") -> None:
    """Assemble a Startpage request.

    To avoid CAPTCHAs we need to send a well formed HTTP POST request with a
    cookie. We need to form a request that is identical to the request built by
    Startpage's search form:

    - in the cookie the **region** is selected
    - in the HTTP POST data the **language** is selected

    Additionally the arguments form Startpage's search form needs to be set in
    HTML POST data / compare ``<input>`` elements: :py:obj:`search_form_xpath`.
    """

    if not query:
        return

    session = sidecar.CACHE.session_get(session_type=session_type)
    if session:
        header_names = ["user-agent"]

        session.upd_headers(params["headers"], names=header_names)
        logger.debug("headers %s updated from WebSession: %s", header_names, params["headers"])
        session.upd_cookies(params["cookies"])
        logger.debug("cookies updated from WebSession: %s", params["cookies"])

    engine_region = traits.get_region(params["searxng_locale"], "en-US")
    engine_language = traits.get_language(params["searxng_locale"], "en")

    params["headers"]["origin"] = base_url
    params["headers"]["referer"] = base_url + "/"

    # HTML form

    args: dict[str, t.Any] = {
        "t": "device",
        "abp": "1",
        "abd": "1",
        "abe": "1",
    }

    if session and session.formdatas:
        for field in session.formdatas[0].fields:
            args[field.name] = field.value

    args["query"] = query
    args["cat"] = startpage_categ
    args["with_date"] = time_range_dict.get(params["time_range"])  # pyright: ignore[reportArgumentType]

    if engine_language:
        args["language"] = engine_language
        args["lui"] = engine_language

    if params["pageno"] > 1:
        args["page"] = params["pageno"]
        args["segment"] = "startpage.udog"

    logger.debug("data: %s", args)

    # Cookies

    lang_homepage = "en"
    _c: OrderedDict[str, str] = OrderedDict()
    _c["date_time"] = "world"
    _c["disable_family_filter"] = safesearch_dict[params["safesearch"]]
    _c["disable_open_in_new_window"] = "0"
    _c["enable_post_method"] = "1"  # hint: POST
    _c["enable_proxy_safety_suggest"] = "1"
    _c["enable_stay_control"] = "1"
    _c["instant_answers"] = "1"
    _c["lang_homepage"] = "s/device/%s/" % lang_homepage
    _c["num_of_results"] = "10"
    _c["suggestions"] = "1"
    _c["wt_unit"] = "celsius"
    if engine_language:
        _c["language"] = engine_language
        _c["language_ui"] = engine_language
    if engine_region:
        _c["search_results_region"] = engine_region
    params["cookies"]["preferences"] = "N1N".join(["%sEEE%s" % x for x in _c.items()])

    logger.debug("cookie preferences: %s", params["cookies"]["preferences"])

    # Request

    params["data"] = args
    params["method"] = "POST"
    params["url"] = search_url


def _parse_published_date(content: str) -> tuple[str, datetime | None]:
    published_date = None

    # check if search result starts with something like: "2 Sep 2014 ... "
    if re.match(r"^([1-9]|[1-2][0-9]|3[0-1]) [A-Z][a-z]{2} [0-9]{4} \.\.\. ", content):
        date_pos = content.find("...") + 4
        date_string = content[0 : date_pos - 5]
        # fix content string
        content = content[date_pos:]

        try:
            published_date = dateutil.parser.parse(date_string, dayfirst=True)
        except ValueError:
            pass

    # check if search result starts with something like: "5 days ago ... "
    elif re.match(r"^[0-9]+ days? ago \.\.\. ", content):
        date_pos = content.find("...") + 4
        date_string = content[0 : date_pos - 5]

        # calculate datetime
        published_date = datetime.now() - timedelta(
            days=int(re.match(r"\d+", date_string).group()),  # type: ignore
        )

        # fix content string
        content = content[date_pos:]

    return content, published_date


def _get_web_result(result: dict[str, str]) -> MainResult:
    content = html_to_text(result.get("description", ""))
    content, publishedDate = _parse_published_date(content)

    return MainResult(
        url=result["clickUrl"],
        title=html_to_text(result["title"]),
        content=content,
        publishedDate=publishedDate,
    )


def _get_news_result(result: dict[str, str]) -> MainResult:

    title = remove_pua_from_str(html_to_text(result["title"]))
    content = remove_pua_from_str(html_to_text(result.get("description", "")))

    r = MainResult(
        url=result["clickUrl"],
        title=title,
        content=content,
    )
    if result.get("date"):
        r["publishedDate"] = datetime.fromtimestamp(float(result["date"]) / 1000)
    if result.get("thumbnailUrl"):
        r["thumbnailUrl"] = base_url + result["thumbnailUrl"]

    return r


def _get_image_result(result: dict[str, str]) -> LegacyResult | None:
    url = result.get("altClickUrl")
    if not url:
        return None

    r = LegacyResult(
        template="images.html",
        url=url,
        title=html_to_text(result["title"]),
        content="",
        img_src=result.get("rawImageUrl"),
        img_format=result.get("format"),
    )
    if result.get("thumbnailUrl"):
        r.thumbnail_src = base_url + result["thumbnailUrl"]

    if result.get("width") and result.get("height"):
        r.resolution = f"{result['width']}x{result['height']}"
    if result.get("filesize"):
        size_str = "".join(filter(str.isdigit, result["filesize"]))
        r.filesize = humanize_bytes(int(size_str))

    return r


def response(resp: "SXNG_Response") -> EngineResults:

    res = EngineResults()

    categ = startpage_categ.capitalize()
    results_raw = "{" + extr(resp.text, f"React.createElement(UIStartpage.AppSerp{categ}, {{", "}})") + "}}"

    if resp.headers.get("Location", "").startswith("https://www.startpage.com/sp/captcha"):
        raise SearxEngineCaptchaException()

    results_json = loads(results_raw)
    results_obj = results_json.get("render", {}).get("presenter", {}).get("regions", {})

    r: MainResult | LegacyResult | None = None
    for results_categ in results_obj.get("mainline", []):
        for item in results_categ.get("results", []):

            if results_categ["display_type"] == "web-google":
                r = _get_web_result(item)
            elif results_categ["display_type"] == "news-bing":
                r = _get_news_result(item)
            elif "images" in results_categ["display_type"]:
                r = _get_image_result(item)
            if r:
                res.add(r)

    return res


def fetch_traits(engine_traits: EngineTraits):
    """Fetch :ref:`languages <startpage languages>` and :ref:`regions <startpage
    regions>` from Startpage."""
    # pylint: disable=too-many-branches

    headers = {
        "User-Agent": gen_useragent(),
        "Accept-Language": "en-US,en;q=0.5",  # bing needs to set the English language
    }
    resp: "SXNG_Response" = get("https://www.startpage.com/do/settings", headers=headers)

    if not resp.ok:
        print("ERROR: response from Startpage is not OK.")

    dom = lxml.html.fromstring(resp.text)

    # regions

    sp_region_names: list[str] = []
    for option in dom.xpath('//form[@name="settings"]//select[@name="search_results_region"]/option'):
        sp_region_names.append(option.get("value"))

    for eng_tag in sp_region_names:
        if eng_tag == "all":
            continue
        babel_region_tag: str = {
            "no_NO": "nb_NO",  # norway
        }.get(eng_tag, eng_tag)

        if "-" in babel_region_tag:
            l, r = babel_region_tag.split("-")
            r = r.split("_")[-1]
            sxng_tag = region_tag(babel.Locale.parse(l + "_" + r, sep="_"))

        else:
            try:
                sxng_tag = region_tag(babel.Locale.parse(babel_region_tag, sep="_"))

            except babel.UnknownLocaleError:
                print("ERROR: can't determine babel locale of startpage's locale %s" % eng_tag)
                continue

        conflict = engine_traits.regions.get(sxng_tag)
        if conflict:
            if conflict != eng_tag:
                print("CONFLICT: babel %s --> %s, %s" % (sxng_tag, conflict, eng_tag))
            continue
        engine_traits.regions[sxng_tag] = eng_tag

    # languages

    x: abc.ItemsView[str, str] = babel.Locale("en").languages.items()  # pyright: ignore[reportUnknownVariableType]
    catalog_engine2code = {name.lower(): lang_code for lang_code, name in x}

    # get the native name of every language known by babel

    for lang_code in filter(lambda lang_code: lang_code.find("_") == -1, babel.localedata.locale_identifiers()):
        native_name = babel.Locale(lang_code).get_language_name()
        if not native_name:
            print(f"ERROR: language name of startpage's language {lang_code} is unknown by babel")
            continue
        native_name = native_name.lower()
        # add native name exactly as it is
        catalog_engine2code[native_name] = lang_code

        # add "normalized" language name (i.e. français becomes francais and español becomes espanol)
        unaccented_name = "".join(filter(lambda c: not combining(c), normalize("NFKD", native_name)))
        if len(unaccented_name) == len(unaccented_name.encode()):
            # add only if result is ascii (otherwise "normalization" didn't work)
            catalog_engine2code[unaccented_name] = lang_code

    # values that can't be determined by babel's languages names

    catalog_engine2code.update(
        {
            # traditional chinese used in ..
            "fantizhengwen": "zh_Hant",
            # Korean alphabet
            "hangul": "ko",
            # Malayalam is one of 22 scheduled languages of India.
            "malayam": "ml",
            "norsk": "nb",
            "sinhalese": "si",
        }
    )

    skip_eng_tags = {
        "english_uk",  # SearXNG lang 'en' already maps to 'english'
    }

    for option in dom.xpath('//form[@name="settings"]//select[@name="language"]/option'):

        eng_tag: str = option.get("value", "")
        if eng_tag in skip_eng_tags:
            continue
        name = (extract_text(option) or "").lower()

        sxng_tag = catalog_engine2code.get(eng_tag)
        if sxng_tag is None:
            sxng_tag = catalog_engine2code[name]

        conflict = engine_traits.languages.get(sxng_tag)
        if conflict:
            if conflict != eng_tag:
                print("CONFLICT: babel %s --> %s, %s" % (sxng_tag, conflict, eng_tag))
            continue
        engine_traits.languages[sxng_tag] = eng_tag
