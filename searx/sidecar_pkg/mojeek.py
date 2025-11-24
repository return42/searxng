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

from .types import SessionType
from .web_session import WebContainer, WebSession, JS, BROWSER

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import WebDriverElement  # type: ignore[reportMissingTypeStubs]
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]


@t.final
class Mojeek(WebContainer):
    """Builds :py:obj:`WebSession` objects for the Brave engines and
    returns it.
    """

    name: ClassVar[SessionType] = "mojeek.com"
    validity_sec: int = 60 * 60 * 24 * 2  # ToDo: 2 days? .. validity period needs to be researched.

    ui: ClassVar[bool] = True  # can be run in batch mode (headless)?
    js_required: ClassVar[bool] = True  # otherwise redirected to html.duckduckgo.com

    user_agent: ClassVar[str] = "Ling-Pong-Ping TV App"

    def build_session_data(self, browser: "BaseWebDriver") -> WebSession | None:
        """ToDo .."""

        from selenium.common.exceptions import JavascriptException  # pylint: disable=import-outside-toplevel

        query = "test 123"
        form_selector = "form[id='searchform']"
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

        browser.visit(f"https://www.mojeek.com/search?q={query}")
        input("press [ENTER] to continue ..")
        s1 = _session_data()
        if not s1.cookies:
            print("""ERROR: missing cookie from "I'm not a robot" dialog.""")
            return None
        return s1
