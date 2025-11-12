# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!  [POC:SideCar]"""

# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations

# msgspec: note that if using PEP 563 “postponed evaluation of annotations”
# (e.g. from __future__ import annotations) only the following spellings will
# work: https://jcristharif.com/msgspec/structs.html#class-variables
from typing import ClassVar
import typing as t

import sys
import time

from .web_session import WebContainer, WebSession, JS, BROWSER

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import WebDriverElement  # type: ignore[reportMissingTypeStubs]
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]


@t.final
class Startpage(WebContainer):
    """Container for startpage.com sessions."""

    name: ClassVar[str] = "startpage.com"
    validity_sec: int = 60 * 60 * 3  # ToDo: 3h? .. validity period needs to be researched.

    # To solve CAPTCHA JS & UI is required, to just get form data, none of both
    # is needed.
    ui: ClassVar[bool] = True
    js_required: ClassVar[bool] = True
    user_agent: ClassVar[str] = "Ping-Pong TV"

    def build_session_data(self, browser: "BaseWebDriver") -> WebSession | None:
        """Builds a :py:obj:`WebSession` object for a startpage.com session and
        returns it.

        Process:

        #. visits https://www.startpage.com/
        #. fill out search form and *click* send button
        #. from the resulting session, the session data is build up from:
           - FormData from the HTML `<form>` element (`Web-API FormData`_)
           - HTTP cookies: startpage.com does not use cookies

        Valuation:

        Startpage does not use cookies, even if a CAPTCHA is required, no
        cookies are used.

        Only the ``sc`` field in the HTML <form> stands out, the value of this
        field might possibly help bypass the bot blocker? ::

            "sc": "OmplqJrfWdUD20"

        My impression is that Startpage -- in *case of 'suspicion'* --
        occasionally directs all queries from one IP to a CAPTCHA, which must be
        answered once to unlock the IP (not the browser session).

        I am not yet aware of what triggers a *suspected case* and whether
        *suspected cases* are triggered less often when an 'sc' is passed along
        still needs to be validated.
        """

        from selenium.common.exceptions import JavascriptException  # pylint: disable=import-outside-toplevel

        form_selector = "form[id='search']"
        captcha_url_prefix = "https://www.startpage.com/sp/captcha"
        bi = BROWSER.info(browser=browser)

        def _session_data() -> WebSession:
            session_data = WebSession(ctx=self.ctx, validity_sec=self.validity_sec)
            session_data.ctx.http_headers.update(bi.headers)
            session_data.cookies = JS.get_cookies(browser=browser)

            try:
                form_data = JS.get_FormData(browser=browser, query_selector=form_selector)
                session_data.formdatas.append(form_data)
            except JavascriptException:
                print(f"ERROR: '{form_selector}' does not match to a HTML <form> ", file=sys.stderr)

            return session_data

        def _css(selector: str, element: "WebDriverElement | BaseWebDriver") -> "list[WebDriverElement]":
            return element.find_by_css(selector)  # type: ignore

        def _wait_captcha_solved():
            print("DEBUG: Wait for the user to solve the CAPTCHA", file=sys.stderr)
            while True:
                sys.stderr.write(".")
                sys.stderr.flush()
                time.sleep(1)
                if not browser.url.startswith(captcha_url_prefix):  # type: ignore
                    sys.stderr.write("\n")
                    sys.stderr.flush()
                    break

        # Process ..

        browser.visit("https://www.startpage.com/")

        if str(browser.url).startswith(captcha_url_prefix):  # type: ignore
            # waits until **the user has solved the challenge**
            _wait_captcha_solved()
            return _session_data()

        msg = f"WARNING: build_session_data({self.name}) - missing CAPTCHA challenge"
        self.messages.append(msg)
        print(msg, file=sys.stderr)

        # build WebSession without a CAPTCHA challenge

        form = _css(form_selector, browser)
        if not form:
            msg = f"ERROR: build_session_data({self.name}) - can't find HTML <form>"
            self.messages.append(msg)
            print(msg, file=sys.stderr)
            return None

        # ToDo: To *validate* the session we send a search query / IDK if this
        # is really needed or if it is enough .. should we enforce a CAPTCHA
        # challenge (how)?

        q_field = _css("input[id='q']", form[0])
        button = _css("button", form[0])
        # button = _css("button[class='search-btn']", form[0])

        q_field[0].fill(self.name)
        button[0].click()

        return _session_data()
