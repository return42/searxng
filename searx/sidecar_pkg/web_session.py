# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!  [POC:SideCar]"""
# pylint: disable=too-few-public-methods, invalid-name, missing-class-docstring, import-outside-toplevel

# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations

# msgspec: note that if using PEP 563 “postponed evaluation of annotations”
# (e.g. from __future__ import annotations) only the following spellings will
# work: https://jcristharif.com/msgspec/structs.html#class-variables
from typing import ClassVar
import typing as t

__all__ = ["WebSession", "WebContainer", "JS", "BROWSER"]

import difflib
import json
import sys
import time
import uuid

import httpx
import msgspec

from .types import HTTP_COOKIE_Type, SessionType, HTTP_HEADER_Type

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import BaseWebDriver  # pyright: ignore[reportMissingTypeStubs]


class WebSession(msgspec.Struct, kw_only=True):
    """Data structure for serializing the state of a web browser session.

    Currently only cookies are in this structure, can be supplemented later with
    other aspects of the session context.
    """

    ctx: "WebSessionCtx"
    uuid: str = ""

    formdatas: "list[FormData]" = []
    """List of ``<form>`` elements found in the document."""

    cookies: HTTP_COOKIE_Type = {}

    time_created: float = 0
    """Unix time the session was created"""

    validity_sec: int = 60 * 60 * 24 * 7  # default 7 days
    """Validity period (in sec.) of the session after it has been created."""

    def __post_init__(self):
        if not self.uuid:
            self.uuid = str(uuid.uuid4())

    def diff(self, other: "WebSession") -> str:
        """Returns the diff of the JSON representations."""
        _self: list[str] = json.dumps(msgspec.to_builtins(self), sort_keys=True, indent=4).splitlines(keepends=True)
        _other: list[str] = json.dumps(msgspec.to_builtins(other), sort_keys=True, indent=4).splitlines(keepends=True)
        diff = difflib.Differ()
        return "".join(diff.compare(_self, _other))

    def upd_cookies(self, cookies: dict[str, str]) -> None:
        """Update the request ``cookies`` dict by the cookies from this
        WebSession."""
        cookies.update(self.cookies)

    def upd_headers(self, headers: HTTP_HEADER_Type, names: list[str] | None = None) -> None:
        """Update the request ``headers`` dict by the HTTP headers from
        WebSession's context.  The value of a existing header will be updated,
        the header name comparison is case-insensitive.  New headers will be
        added in *lowercase*!

        .. note::

           Each HTTP header field consists of a name followed by a colon (":")
           and the field value.  Field names are case-insensitive [rfc2616_].

        .. _rfc2616: https://www.rfc-editor.org/rfc/rfc2616.html#section-4.2

        """
        names = [_.lower() for _ in (names or [])]

        for name, value in self.ctx.http_headers.items():
            name = name.lower()
            if names and name not in names:
                continue
            exists = False
            for k in headers.keys():
                if k.lower() == name:
                    headers[k] = value
                    exists = True
            if not exists:
                headers[name] = value


class WebSessionCtx(msgspec.Struct, kw_only=True):
    """The context in which the session data is to be constructed."""

    session_type: SessionType
    http_headers: HTTP_HEADER_Type = {}
    """Header names have to be lower case!!"""

    js_required: bool | None = None
    """A flag that indicates whether JavaScript had to be activated in the
    browser during the creation of the session data or not. The value is set by
    the process that establishes the session.
    """

    def __post_init__(self):
        self.http_headers = {k.lower(): v for k, v in self.http_headers.items()}


class FormData(msgspec.Struct, kw_only=True):
    """The fields read from a HTML `<form>` element, compare `Web-API
    FormData`_.

    .. _Web-API FormData: https://developer.mozilla.org/en-US/docs/Web/API/FormData
    """

    fields: "list[FormField]" = []

    def get(self, name: str) -> "FormField | None":
        for field in self.fields:
            if field.name == name:
                return field
        return None

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> "FormData":
        fields = [FormField(name=k, value=v) for k, v in d.items()]
        return cls(fields=fields)

    @property
    def as_dict(self) -> dict[str, str]:
        return {i.name: i.value for i in self.fields}


class FormField(msgspec.Struct, kw_only=True):
    """A input field from a HTML `<form>` element."""

    name: str
    value: str | None


class WebContainer(msgspec.Struct, kw_only=True):
    """Container for storing session data from a web browser session."""

    ctx: WebSessionCtx
    sessions: list[WebSession] = []

    ok: bool = False
    messages: list[str] = []

    ui: ClassVar[bool] = False
    """Can sessions of this type be generated automatically, or is a UI required
    for this (for example, to allow the user to solve a CAPTCHA)?
    """

    js_required: ClassVar[bool] = False
    """:py:obj:`WebSessionCtx.js_required`"""

    # ToDo: for the POC we use a hard coded default
    user_agent: ClassVar[str] = "Mozilla/5.0 (X11; Linux x86_64; rv:144.0) Gecko/20100101 Firefox/144.0"

    def __post_init__(self):
        self.init_ctx(self.ctx)

    @classmethod
    def init_ctx(cls, ctx: WebSessionCtx) -> None:
        ctx.js_required = cls.js_required
        ctx.http_headers["user-agent"] = cls.user_agent

    @classmethod
    def from_url(cls, sidecar_url: str, ctx: WebSessionCtx, n: int, timeout: int) -> "WebContainer":
        """Factory to build a :py:obj:`WebContainer` object with ``n`` sessions in.

        Sends a HTTP GET (httpx) request to SearXNG's sandbox server and returns
        the container object received from remote."""

        # see client endpoint web_sessions_get
        url = f"{sidecar_url}/engine/Container/from_browser/{n}"

        # 1. create container obj (builtin types)
        con_obj = msgspec.to_builtins(cls(ctx=ctx))

        # 2. send obj to remote
        print(f"DEBUG: send request to {url}", file=sys.stderr)
        try:
            resp = httpx.post(url, timeout=timeout, json=con_obj)
            # 3. receive (JSON) of obj and return the new instance
            con = msgspec.json.decode(resp.text, type=cls)
        except msgspec.DecodeError:
            con = cls(ctx=ctx)
            con.ok = False
            con.messages.append(
                f"got 'HTTP {resp.status_code}' from {url}",  # pyright: ignore[reportPossiblyUnboundVariable]
            )

        except httpx.HTTPError as exc:
            con = cls(ctx=ctx)
            con.ok = False
            con.messages.append(f"got '{exc}' from {url}")
        return con

    @classmethod
    def from_browser(cls, browser: "BaseWebDriver", ctx: WebSessionCtx, n: int) -> "WebContainer":
        """Factory to build a :py:obj:`WebContainer` object with ``n`` sessions in."""
        self = cls(ctx=ctx)
        for _ in range(n):
            session_data = self.build_session_data(browser)
            if session_data:
                session_data.time_created = time.time()
                self.sessions.append(session_data)

            # prepare for next loop (reset browser's cookies and site data)
            self.reset_browser(browser)

        if self.sessions:
            self.ok = True
        return self

    def build_session_data(
        self,
        browser: "BaseWebDriver",  # pyright: ignore[reportUnusedParameter]
    ) -> WebSession | None:
        """Must be implemented in the heir.  Opens a session in the web
        ``browser`` and returns a :py:obj:`WebSession` object."""

        raise NotImplementedError()

    @classmethod
    def get_browser(
        cls,
        user_agent: str,
        socks5: str = "",
        headless: bool = False,
        js_required: bool = True,
    ) -> "BaseWebDriver":

        from selenium import webdriver
        from selenium.webdriver.firefox.options import Options as FirefoxOptions
        from splinter import Browser  # type: ignore

        ffox_opts: FirefoxOptions = FirefoxOptions()
        ffox_opts.set_preference("devtools.jsonview.enabled", False)
        ffox_opts.set_preference("javascript.enabled", js_required)
        if headless:
            ffox_opts.add_argument("--headless")
        if socks5:
            # https://gist.github.com/turicas/911cef28a9fa8c8872c6ff1c98a4abe7
            proxy = webdriver.Proxy(raw={"socksProxy": f"{socks5}", "socksVersion": 5})
            ffox_opts.set_capability("proxy", proxy.to_capabilities())  # pyright: ignore[reportUnknownMemberType]

        browser: "BaseWebDriver" = Browser(  # type: ignore[reportAssignmentType]
            "firefox",
            options=ffox_opts,
            user_agent=user_agent,
        )
        return browser

    def reset_browser(self, browser: "BaseWebDriver"):

        try:
            browser.cookies.delete_all()
            localStorage = str(JS.get_localStorage(browser))
            if len(localStorage) > 200:
                localStorage = localStorage[:100] + " ... " + localStorage[-100:]
            print(f"DEBUG: delete cookies & clean localStorage -->{localStorage}<--", file=sys.stderr)
            JS.clear_localStorage(browser=browser)
        except Exception as exc:
            print(f"WARNING: clear browser session failed: {exc}", file=sys.stderr)


class BrowserInfo(msgspec.Struct):

    public_ip: str = ""
    public_port: int = 0
    """Public (outgoing) IP & port number used for browser requests."""

    headers: HTTP_HEADER_Type = {}
    """HTTP headers sent by the browser.  FIXME: see BROWSER.info --> can we
    send HTTP Headers (Cookies and others) to https://echo.free.beeceptor.com/
    and become an echo?"""


class BROWSER:
    """Tools to introspect the web browser.

    The class currently serves only as a namespace.
    """

    @staticmethod
    def ctx_id(ctx: WebSessionCtx) -> str:
        """Generates an ID for the given session context.

        The ID is constructed from the session type and the setup data of the
        web browser relevant to the browser session (e.g. the HTTP
        ``User-Agent``).  The ID can be used, for example, to select browsers
        with a very specific setup from a browser pool.
        """
        key = {
            "session_type": ctx.session_type,
            "http_headers": {
                "user-agent": ctx.http_headers.get("user-agent", ""),
            },
        }
        return msgspec.json.encode(key, order="sorted").decode("utf-8")

    @staticmethod
    def info(browser: "BaseWebDriver") -> BrowserInfo:
        # Beeceptor's HTTP echo server reflects the content of your HTTP
        # request, making it easy to debug. Perfect for testing and fine-tuning
        # your API calls! https://beeceptor.com/resources/http-echo/
        browser.visit("https://echo.free.beeceptor.com/")
        data = msgspec.json.decode(browser.find_by_xpath("//pre").text)  # pyright: ignore[reportUnknownMemberType]
        # Use lowercase for header names!
        headers: dict[str, str] = {k.lower(): v for k, v in data.get("headers", {}).items()}
        for h in ["host", "alt-used", "via"]:
            headers.pop(h, None)
        ip, port = (data.get("ip", "").rsplit(":", 1) + ["0"])[:2]
        return BrowserInfo(public_ip=ip.strip("[]"), public_port=int(port), headers=headers)


class JS:
    """Execute JS snippets in the browser session.

    The class currently serves only as a namespace.
    """

    localStorage: str = """
    return Array.apply(0, new Array(localStorage.length)).map(
      function (o, i) {
        return localStorage.getItem(localStorage.key(i));
      }
    )"""

    search_form: str = """
    ret_val = new Array();
    form_data = new FormData(document.querySelector("%(selector)s"));
    for (const i of form_data.entries()) {
      ret_val.push([i[0], i[1]]);
    }
    return ret_val
    """

    @staticmethod
    def exec(browser: "BaseWebDriver", script: str) -> t.Any:
        # print(f"DEBUG: exec JS: -->{script}<--", file=sys.stderr)
        return browser.execute_script(script)  # pyright: ignore[reportUnknownVariableType]

    @staticmethod
    def get_localStorage(browser: "BaseWebDriver") -> t.Any:
        return JS.exec(browser, JS.localStorage)

    @staticmethod
    def clear_localStorage(browser: "BaseWebDriver") -> None:
        JS.exec(browser, "localStorage.clear()")

    @staticmethod
    def get_cookies(browser: "BaseWebDriver") -> HTTP_COOKIE_Type:
        """HTTP cookies (both, JS and HttpOnly_ cookies)

        .. _HttpOnly: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#httponly
        """
        # document.cookie (JS) does not contain the HttpOnly cookies!
        # cookies = JS.exec(browser, "return document.cookie")
        cookies = browser.cookies.all()
        return cookies

    @staticmethod
    def get_FormData(browser: "BaseWebDriver", query_selector: str) -> FormData:
        form_data = FormData()
        script = JS.search_form % {"selector": query_selector}

        ok = False
        fields: list[FormField] = []
        while not ok:
            ok = True
            fields = []

            n_v_pairs: list[tuple[str, str]] = JS.exec(browser, script)
            if not n_v_pairs:
                print(f"WARNING: HTML <form> {query_selector} does not exists", file=sys.stderr)
                break

            for name, value in n_v_pairs:
                if name in ("query",):  # FIXME
                    continue
                # sometimes we get "NaN" string for some fields ...
                # https://developer.mozilla.org/en-US/docs/Glossary/Falsy
                if value != "NaN":
                    fields.append(FormField(name=name, value=value))
                    continue
                # .. executing the JS a second time (with a delay) will fix it.
                print("WARNING: got NaN, retry to execute JS.search_form ..", file=sys.stderr)
                time.sleep(1)
                ok = False
                break

        form_data.fields.extend(fields)
        return form_data
