# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!  [POC:SideCar]"""

# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations

# msgspec: note that if using PEP 563 “postponed evaluation of annotations”
# (e.g. from __future__ import annotations) only the following spellings will
# work: https://jcristharif.com/msgspec/structs.html#class-variables
from typing import ClassVar
import typing as t

import time

from .types import SessionType
from .web_session import WebContainer, WebSession, JS, BROWSER

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import WebDriverElement  # type: ignore[reportMissingTypeStubs]
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]


@t.final
class Loc(WebContainer):
    """Container for library of congress engine"""

    name: ClassVar[SessionType] = "loc.gov"
    validity_sec: int = 60 * 60 * 3  # ToDo: 3h? .. validity period needs to be researched.

    ui: ClassVar[bool] = False  # can be run in batch mode (headless)?
    js_required: ClassVar[bool] = True

    # Assumption: The user agent should not correspond to the common web
    # browsers, for which datadome has very specific validation profiles. If the
    # user agent is unknown, then only a general validation profile can be
    # applied.
    user_agent: ClassVar[str] = "Ping-Pong TV"

    def build_session_data(self, browser: "BaseWebDriver") -> WebSession | None:
        """ToDo .. Cloudflare CAPTCHA"""

        bi = BROWSER.info(browser=browser)

        def _session_data() -> WebSession:
            session_data = WebSession(ctx=self.ctx, validity_sec=self.validity_sec)
            session_data.ctx.http_headers.update(bi.headers)
            session_data.cookies = JS.get_cookies(browser=browser)
            return session_data

        browser.visit("https://loc.gov/photos/")
        time.sleep(1)
        browser.visit("https://www.loc.gov/photos/?sp=1&q=foo&fo=json")
        input("press [ENTER] to continue ..")
        return _session_data()
