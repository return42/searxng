# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!  [POC:SideCar]"""

# HINT: the current solution (implemented below) is based on the
# GOOGLE_ABUSE_EXEMPTION cookie .. in this process, I haven't seen one of the
# cookies documented here:
#
# - https://policies.google.com/technologies/cookies ..
#
# _Secure-ENID
# ------------
# most people who use Google services have a cookie called ‘NID’ or
# ‘_Secure-ENID’ in their browsers, depending on their cookie choices. These
# cookies are used to remember your preferences and other information, such as
# your preferred language, how many results you prefer to have shown on a search
# results page (for example, 10 or 20), and whether you want to have Google’s
# SafeSearch filter turned on.
#
# Each ‘NID’ cookie expires 6 months from a user’s last use, while the
# ‘_Secure-ENID’ cookie lasts for 13 months. Cookies called ‘VISITOR_INFO1_LIVE’
# and ‘__Secure-YEC’ serve a similar purpose for YouTube and are also used to
# detect and resolve problems with the service. These cookies last for 6 months
# and for 13 months, respectively.
# ..
# Google services also use ‘NID’ and ‘_Secure-ENID’ cookies on Google Search,
# and ‘VISITOR_INFO1_LIVE’ and ‘__Secure-YEC’ cookies on YouTube, for
# analytics. Google mobile apps may also use unique identifiers, such as the
# ‘Google Usage ID’, for analytics.
#
# CGIC
# ----
# Cookies and similar technologies may also be used to improve the performance
# of Google services. For example, the ‘CGIC’ cookie improves the delivery of
# search results by autocompleting search queries based on a user’s initial
# input. This cookie lasts for 6 months.
#
# SID, HSID
# ---------
# For example, cookies called ‘SID’ and ‘HSID’ contain digitally signed and
# encrypted records of a user’s Google Account ID and most recent sign-in
# time. The combination of these cookies allows Google to block many types of
# attack, such as attempts to steal the content of forms submitted in Google
# services. These cookies last for 2 years.
#
# pm_sess, YSC, __Secure-YEC
# --------------------------
# Some cookies and similar technologies are used to detect spam, fraud, and
# abuse. For example, the ‘pm_sess’ and ‘YSC’ cookies ensure that requests
# within a browsing session are made by the user, and not by other sites. These
# cookies prevent malicious sites from acting on behalf of a user without that
# user’s knowledge. The ‘pm_sess’ cookie lasts for 30 minutes, while the ‘YSC’
# cookie lasts for the duration of a user’s browsing session. The ‘__Secure-YEC’
# and ‘AEC’ cookies are used to detect spam, fraud, and abuse to help ensure
# advertisers are not incorrectly charged for fraudulent or otherwise invalid
# impressions or interactions with ads, and that YouTube creators in the YouTube
# Partner Program are remunerated fairly. The ‘AEC’ cookie lasts for 6 months
# and the ‘__Secure-YEC’ cookie lasts for 13 months.


# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations

# msgspec: note that if using PEP 563 “postponed evaluation of annotations”
# (e.g. from __future__ import annotations) only the following spellings will
# work: https://jcristharif.com/msgspec/structs.html#class-variables
from typing import ClassVar
import typing as t

import sys
import time

from .web_session import WebContainer, WebSession, JS

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import WebDriverElement  # type: ignore[reportMissingTypeStubs]
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]


@t.final
class Google(WebContainer):
    """Container for google.com sessions."""

    name: ClassVar[str] = "google.com"
    validity_sec: int = 60 * 60 * 2
    """The GOOGLE_ABUSE_EXEMPTION seems to be valid for about 2 hours."""

    ui: ClassVar[bool] = True
    js_required: ClassVar[bool] = True
    # user_agent: ClassVar[str] = "Ping-Pong TV"

    def build_session_data(self, browser: "BaseWebDriver") -> WebSession | None:
        """Builds a :py:obj:`WebSession` object for a google.com session and
        returns it.

        Process:

        #. visit https://www.google.com/
        #. answer the cookie dialog (click *accept* button)
        #. enforces a CAPTCHA challenge ``https://www.google.com/sorry ..``
        #. waits until **the user has solved the challenge**
        #. from the resulting session, the session data is build up from:
           - FormData from the HTML `<form>` element (`Web-API FormData`_)
           - HTTP cookies (both, JS and HttpOnly_ cookies)

        .. _HttpOnly: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#httponly

        The ``GOOGLE_ABUSE_EXEMPTION`` cookie requires further investigation.
        The value includes, among other things, the IP address and a timestamp.

        Example::

          {
            'SOCS': 'CAESHAgBEhJnd3NfMjAyNTExMDYtMF9SQzEaAmRlIAEaBgiAs7_IBg',
            'GOOGLE_ABUSE_EXEMPTION': 'ID=..:TM=<unix timestamp>:C=R:IP=<the request comes from>-:S=..',
             'DV': 'g1BocSViDSQkQIF0XFQkBVhtGXeQptnoqshm1sxFHlUcAAA'
          }

        Drawbacks ``GOOGLE_ABUSE_EXEMPTION``:

        - The is only valid for requests from the ``IP``
        - seems to be valid for about 2 hours.

        Alternatives::

        ???
        """

        from selenium.common.exceptions import JavascriptException  # pylint: disable=import-outside-toplevel

        form_selector = "form"
        # bi = BROWSER.info(browser=browser)

        def _session_data() -> WebSession:
            session_data = WebSession(ctx=self.ctx, validity_sec=self.validity_sec)
            # Google blocks, when we copy headers from this browser
            # session_data.ctx.http_headers.update(bi.headers)
            session_data.cookies = JS.get_cookies(browser=browser)

            try:
                form_data = JS.get_FormData(browser=browser, query_selector=form_selector)
                session_data.formdatas.append(form_data)
            except JavascriptException:
                print(f"ERROR: '{form_selector}' does not match to a HTML <form> ", file=sys.stderr)

            return session_data

        def _css(selector: str, element: "WebDriverElement | BaseWebDriver") -> "list[WebDriverElement]":
            return element.find_by_css(selector)  # type: ignore

        # visit https://www.google.com/

        browser.visit("https://www.google.com/")

        # . answers the cookie dialog
        accept_button = _css("button[id='W0wltc']", browser)
        if not accept_button or len(accept_button) > 1:
            msg = f"ERROR: build_session_data({self.name}) - can't find the button to reject cookies"
            self.messages.append(msg)
            print(msg, file=sys.stderr)
            return None
        accept_button[0].click()

        # enforces a CAPTCHA challenge ``https://www.google.com/sorry ..``

        browser.visit("https://www.google.com/search?q=foo")

        if not str(browser.url).startswith("https://www.google.com/sorry"):  # type: ignore
            msg = f"ERROR: build_session_data({self.name}) - missing CAPTCHA challenge"
            self.messages.append(msg)
            print(msg, file=sys.stderr)
            return None

        # waits until **the user has solved the challenge**

        print("DEBUG: Wait for the user to solve the CAPTCHA", file=sys.stderr)
        while True:
            sys.stderr.write(".")
            sys.stderr.flush()
            time.sleep(1)
            if not browser.url.startswith("https://www.google.com/sorry"):  # type: ignore
                sys.stderr.write("\n")
                sys.stderr.flush()
                break

        time.sleep(1)
        # from the resulting session, the session data is build up:
        return _session_data()
