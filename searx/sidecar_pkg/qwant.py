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

from .types import SessionType
from .web_session import WebContainer, WebSession, JS, BROWSER

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import WebDriverElement  # type: ignore[reportMissingTypeStubs]
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]


@t.final
class Qwant(WebContainer):
    """Container for gwant.com sessions.

    # FIXME: a valid datadome cookie is needed!!!

    """

    name: ClassVar[SessionType] = "qwant.com"
    validity_sec: int = 60 * 60 * 3  # ToDo: 3h? .. validity period needs to be researched.

    ui: ClassVar[bool] = True
    js_required: ClassVar[bool] = True

    # Assumption: The user agent should not correspond to the common web
    # browsers, for which datadome has very specific validation profiles. If the
    # user agent is unknown, then only a general validation profile can be
    # applied.
    user_agent: ClassVar[str] = "Ping-Pong TV"

    def build_session_data(self, browser: "BaseWebDriver") -> WebSession | None:
        """Builds a :py:obj:`WebSession` object for a qwant.com session and
        returns it.

        Process:

        #. visits qwant.com
        ... ??? ...
        #. from the resulting session, the session data is build up from:
           - FormData from the HTML `<form>` element (`Web-API FormData`_)
           - HTTP cookies (both, JS and HttpOnly_ cookies)

        .. _HttpOnly: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#httponly
        """

        from selenium.common.exceptions import JavascriptException  # pylint: disable=import-outside-toplevel

        form_selector = "form"
        bi = BROWSER.info(browser=browser)
        input("Press Enter to continue...")

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

        browser.visit("https://www.qwant.com/")
        time.sleep(1)

        form = _css(form_selector, browser)
        if not form:
            msg = f"ERROR: build_session_data({self.name}) - can't find HTML <form>"
            self.messages.append(msg)
            print(msg, file=sys.stderr)
            return None

        q_field = _css("input[name='q']", form[0])
        button = _css("button", form[0])

        if len(button) != 1 or len(q_field) != 1:
            msg = f"ERROR: build_session_data({self.name}) - can't find the input field / send button"
            self.messages.append(msg)
            print(msg, file=sys.stderr)
            return None

        q_field[0].fill(self.name)
        button[0].click()

        # if s1.cookies.get("datadome"):
        #     print("DEBUG: Wait for the user to solve the CAPTCHA", file=sys.stderr)
        #     while True:
        #         s2 = _session_data()
        #         sys.stderr.write(".")
        #         sys.stderr.flush()
        #         if s1.cookies.get("datadome") != s2.cookies.get("datadome"):
        #             print(
        #                 f"DEBUG: datadome:  {s1.cookies.get('datadome')} <--> {s2.cookies.get('datadome')}",
        #                 file=sys.stderr,
        #             )
        #             sys.stderr.write("\n")
        #             sys.stderr.flush()
        #             break
        #         time.sleep(1)

        # FIXME: a valid datadome cookie is needed!!!  In my tests, Qwant
        # detected the selenium session and blocks the Session.  The datadome
        # cookie in this session isn't able to pass Qwant's bot detection.

        input("Press Enter to continue...")

        return _session_data()
