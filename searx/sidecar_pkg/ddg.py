# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!  [POC:SideCar]"""

# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations

# msgspec: note that if using PEP 563 “postponed evaluation of annotations”
# (e.g. from __future__ import annotations) only the following spellings will
# work: https://jcristharif.com/msgspec/structs.html#class-variables
from typing import ClassVar
import typing as t

import pdb
import sys
import string
import random
import time
from urllib.parse import urlencode

import httpx
import lxml.html

from .types import SessionType
from .web_session import WebContainer, WebSession, JS, FormField

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import WebDriverElement  # type: ignore[reportMissingTypeStubs]
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]


x = "".join(random.choice(string.digits) for _ in range(7))
random_user_agent = f"Ling Long TV App ({x})"


@t.final
class DuckDuckGo(WebContainer):
    """Builds :py:obj:`WebSession` objects for the DuckDuckGo engines and
    returns it.

    WebSessions would have to be created anew for each search term, which
    doesn't make sense .. in the SearXNG engines, it's better to read the vqd
    values from the forms, which are returned by DDG.

    .. note::

       The implementations in this module are intended solely for reverse
       engineering.
    """

    name: ClassVar[SessionType] = "duckduckgo.com"
    validity_sec: int = 60 * 60 * 24 * 2  # ToDo: 2 days? .. validity period needs to be researched.

    ui: ClassVar[bool] = True  # can be run in batch mode (headless)?
    js_required: ClassVar[bool] = True  # otherwise redirected to html.duckduckgo.com

    user_agent: ClassVar[str] = "Ling Long TV App"

    @classmethod
    def _get_browser(
        cls, user_agent: str, socks5: str = "", headless: bool = False, js_required: bool = True
    ) -> "BaseWebDriver":
        return WebContainer.get_browser(user_agent, socks5)

    @classmethod
    def get_browser(cls, *args, **kwargs) -> t.Any:  # type: ignore
        return (args, kwargs)

    def build_session_data(self, browser_args) -> WebSession | None:  # type: ignore
        """ToDo .."""

        browser: "BaseWebDriver"
        query = "foo"
        params = {"headers": {}}

        from selenium.common.exceptions import JavascriptException  # pylint: disable=import-outside-toplevel
        from selenium import webdriver

        # form_selector = "form:has(> input[name='vqd']"
        # form_selector = "form"

        # ---------------------------------------------------------------------
        # headers
        # ---------------------------------------------------------------------

        params["headers"]["Accept-Encoding"] = "gzip, deflate, bz"
        # The https://duckduckgo.com/i.js script and the other scripts on DDG
        # seem to have a special bot protection (based on UA header?):
        print(f"User-Agent: {random_user_agent}")
        params["headers"]["User-Agent"] = random_user_agent

        # params["headers"]["Accept"] = "*/*"
        # params["headers"]["X-Requested-With"] = "XMLHttpRequest"
        # params["headers"]["Referer"] = "https://duckduckgo.com/"
        # params["headers"]["Host"] = "duckduckgo.com"
        # params["headers"]["Accept-Language"] = "de,en;q=0.5"
        # params["headers"]["Sec-Fetch-Dest"] = "empty"
        # params["headers"]["Sec-Fetch-Mode"] = "cors"
        # params["headers"]["Sec-Fetch-Site"] = "same-origin"
        # params["headers"]["Sec-Fetch-User"] = "?1"
        # params["headers"]["Sec-GPC"] = "1"
        # params["headers"]["TE"] = "trailers"
        # params["headers"]["Cache-Control"] = "no-cache"
        # params["headers"]["Pragma"] = "no-cache"

        # ---------------------------------------------------------------------
        # Try to fetch vqd value and emulate the XMLHttpRequest from DDG origin
        # image search.
        # ---------------------------------------------------------------------

        # Fetch required data from intro page

        intro_url = (
            f"https://duckduckgo.com/?origin=funnel_home_website&t=h_&q={ query + ' fixme'}&ia=images&iax=images"
        )
        intro_resp = httpx.get(intro_url, headers=params["headers"])
        # doc: lxml.html.HtmlElement = lxml.html.fromstring(resp.text)
        print(f"INFO: got HTTP {intro_resp.status_code} from {intro_url}")

        # vqd

        start_pos: int = intro_resp.text.index("vqd") + 5
        vqd = intro_resp.text[start_pos : start_pos + 41]
        print(f"INFO: vqd - {vqd}")

        # unlock JS API

        # TODO .. how to unlock API?

        # - the t.js script is for adds and be ignored
        #
        # start_pos: int = resp.text.index("nrj('") + 5
        # end_pos: int = start_pos + resp.text[start_pos:].index("');")
        # unlock_api_url = f"https://duckduckgo.com{resp.text[start_pos: end_pos]}"

        # - post3.html

        unlock_api_url = "https://duckduckgo.com/post3.html"
        print(f"INFO: unlock API post3.html - {unlock_api_url}")
        resp_unlock = httpx.get(unlock_api_url, headers=params["headers"])
        print(f"INFO: unlock API post3.html - got HTTP {resp_unlock.status_code}")
        doc: lxml.html.HtmlElement = lxml.html.fromstring(resp_unlock.text)

        # - post3.html JS

        js_url = f"https://duckduckgo.com{doc.xpath('//script/@src')[0]}"
        resp_js = httpx.get(js_url, headers=params["headers"])
        print(f"INFO: unlock API - {js_url} got HTTP {resp_unlock.status_code}")

        # Alternative that works: unlock JS API via browser ..

        if True:  # FIXME set to True to load once into the browser (to unleash JS API)
            args, kwargs = browser_args
            kwargs["user_agent"] = random_user_agent
            # The API is activated by accessing intro page it in the browser,
            # and it doesn't matter what the query is.
            _intro_url = f"https://duckduckgo.com/?origin=funnel_home_website&t=h_&q={query}&ia=images&iax=images"
            browser = self._get_browser(*args, **kwargs)
            input("Enable developer console in Firefox and press ENTER to continue ..")
            browser.visit(_intro_url)
            input("Press ENTER to continue ..")
            browser.quit()
        else:
            # FIXME: what else do we need to request to unleash JS API??
            input("Press ENTER to continue ..")

            url_list = [
                "https://duckduckgo.com/assets/logo_header.v109.svg",
                "https://duckduckgo.com/dist/wpl.main.f02743ba7d5cbde4f37d.css",
            ]

            for url in url_list:
                httpx.get(unlock_api_url, headers=params["headers"])

        # ---------------------------------------------------------------------
        # XHTMLRequest
        # ---------------------------------------------------------------------

        args: dict[str, str | int] = {
            "o": "json",
            "q": query + " fixme",  # FIXME
            "l": "de-de",  # FIXME
            "p": 1,  # FIXME
            "ct": "DE",  # FIXME
            "bpia": 1,
            "vqd": vqd,
        }

        # FIXME: this ``i.js`` request only works if ddg has been accessed in
        # the browser at least once from the IP, using the exactly same user
        # agent.

        url = f"https://duckduckgo.com/i.js?{urlencode(args)}"

        # ---------------------------------------------------------------------
        # fetch images ..
        # ---------------------------------------------------------------------

        print(f"scrap image links from: {url}")
        resp = httpx.get(url, headers=params["headers"])
        if resp.status_code != 200:
            print(
                f"ERROR can't handle HTTP: {resp.status_code} received message --> {resp.text[:100]} ...",
                file=sys.stderr,
            )
            return None

        for c, item in enumerate(resp.json()["results"]):
            print(f"{c}. image url: {item['image']}")

        # - vqd (str): Validation query digest / a hash of the search term
        #
        # WebSessions would have to be created anew for each search term, which
        # doesn't make sense... it's better to read the vqd values from the
        # forms in the SearXNG engine, which are returned by DDG.
        return None
