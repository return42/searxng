# SPDX-License-Identifier: AGPL-3.0-or-later
"""Code to manage the session data that is (or can be) used in the requests
of the engines.

  THIS IS A POC!!

There is a command-line interface for *sessions*, which can be run in a SearXNG
developer environment::

   $ ./manage dev.env
   (dev.env)$ python -m searx.enginelib sidecar --help

Start *SideCar* server::

   (dev.env)$ python -m searx.enginelib sidecar

Test request from client.  Request (three) google.com sessions::

   (dev.env)$ python -m searx.enginelib sidecar sessions.get google.com --url "http://127.0.0.2:50000"

"""
# pylint: disable=too-few-public-methods,disable=invalid-name

import pdb  # FIXME

import typing as t

# ClassVar must be explicitly imported; using t.ClassVar does not correctly
# recognize the type definition!
# - https://jcristharif.com/msgspec/structs.html#class-variables
from typing import ClassVar

import sys

import msgspec
import typer
import flask
from typing_extensions import Annotated
import timeit

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import DriverAPI  # pyright: ignore[reportMissingTypeStubs]


SIDECAR_LISTEN = "127.0.0.2", 50000
"""Host and port SearXNG's sidecar server listens on."""

SIDECAR_URL = f"http://127.0.0.2:{SIDECAR_LISTEN[1]}"
"""Base URL for requests to SearXNG's sidecar server."""


class Cookie(msgspec.Struct, kw_only=True):
    """Data type for a cookie in a *session context*."""

    name: str
    value: str
    domain: str
    expiry: int


class SessionData(msgspec.Struct, kw_only=True):
    """Data structure for a *session context*.

    Currently only cookies are in this structure, can be supplemented later with
    other aspects of the session context.
    """

    cookies: list[Cookie] = []

    @property
    def cookies_as_dict(self) -> dict[str, str]:
        ret_val: dict[str, str] = {}
        for c in self.cookies:
            ret_val[c.name] = c.value
        return ret_val


JS_localStorage = """
return Array.apply(0, new Array(localStorage.length)).map(
  function (o, i) {
    return localStorage.getItem(localStorage.key(i));
  }
)
"""


class SideCarJob(msgspec.Struct, kw_only=True):
    """Data type used to transport (JSON) a list of session data."""

    name: ClassVar[str] = ""
    version: ClassVar[int] = 1

    sessions: list[SessionData] = []
    ok: bool = False
    messages: list[str] = []

    def __post_init__(self):
        # print(f"DEBUG: {self.__struct_fields__}") # FIXME
        if not self.name:
            raise ValueError("The name of the container is not given (implementation issue).")

    @classmethod
    def from_request(cls, sidecar_url: str, n: int, timeout: int) -> "SideCarJob":
        """Factory to build a :py:obj:`Container` object with ``n`` sessions in
        on remote.  Sends a HTTP GET (httpx) request to SearXNG's sandbox server
        and returns the container object received from remote.
        """
        # endpoint web_sessions_get
        url = f"{sidecar_url}/sessions/get/{cls.name}/{n}/"
        print(f"DEBUG: send request to {url}", file=sys.stderr)
        try:
            resp = httpx.get(url, timeout=timeout)
            job = msgspec.json.decode(resp.text, type=cls)
        except httpx.HTTPError as exc:
            job = cls(ok=False, messages=[f"got '{exc}' from {url}"])
        return job

    @classmethod
    def from_browser(cls, browser: "DriverAPI", n: int) -> "SideCarJob":
        """Factory to build a :py:obj:`Container` object with ``n`` sessions in."""
        con = cls()
        for _ in range(n):
            session_data = con.build_session_data(browser)
            if session_data:
                con.sessions.append(session_data)

            # FIXME log content of browser's localStorage
            # localStorage = str(browser.execute_script(JS_localStorage))[:100]
            # print(f"DEBUG: localStorage --> {localStorage}", file=sys.stderr)

            # prepare for next loop (reset browser's cookies and site data)
            #browser.cookies.delete_all()
            #browser.execute_script("""localStorage.clear()""")

        if con.sessions:
            con.ok = True
        return con

    def build_session_data(self, browser: "DriverAPI") -> SessionData:
        """Must be implemented in the heir.  Opens a session in the web
        ``browser`` and returns a :py:obj:`SessionData` object."""

        raise NotImplementedError()


## searx.engines.google
## --------------------


@t.final
class Google(SideCarJob):

    name: ClassVar[str] = "google.com"

    def build_session_data(self, browser: "DriverAPI") -> SessionData:
        """Visits google.com, answers the cookie dialog, builds a
        :py:obj:`SessionData` object and returns it.
        """
        # https://splinter.readthedocs.io/en/latest/

        data = SessionData()
        browser.visit("https://www.google.com")

        button = browser.find_by_xpath("//button[@id='W0wltc']")
        if not button or len(button) > 1:
            msg = f"ERROR: build_session_data({self.name}) - can't find the button to reject cookies"
            self.messages.append(msg)
            print(msg, file=sys.stderr)
            return data

        # To *validate* the __Secure-ENID we have to click the cookie (reject)
        # button ..
        button[0].click()  # type: ignore

        for item in browser.cookies.driver.get_cookies():
            data.cookies.append(
                Cookie(
                    name=item["name"],
                    value=item["value"],
                    domain=item["domain"],
                    expiry=item["expiry"],
                )
            )
        return data


## Sidecar tools & services
## ------------------------

import httpx

MAP_JOB_TYPES: dict[str, type[SideCarJob]] = {
    Google().name: Google,
}
GLOBAL_BROWSER: "DriverAPI" = None  # type: ignore

cli = typer.Typer()
web = flask.Flask("sessions")


def init():
    global GLOBAL_BROWSER
    from splinter import Browser
    from selenium import webdriver

    ffox_opts = webdriver.firefox.options.Options()
    # FIXME ..
    # ffox_opts.add_argument("--headless")

    GLOBAL_BROWSER = Browser("firefox", options=ffox_opts)

    # TODO: set HTTP-headers
    # - https://www.zenrows.com/blog/web-scraping-headers#common-http-headers
    #   request.headers["Accept-Language"] = "en"
    # - to test headers, see response of:: GLOBAL_BROWSER.visit("https://httpbin.io/headers")
    #
    # Selenium (the 'Browser' from splinter) does not support to modify HTTP
    # headers! .. Alternatives?
    # - https://pydoll.tech/  (Chrom)
    # - https://playwright.dev/python (cross browser!)
    #   https://playwright.dev/python/docs/api/class-request#request-all-headers
    #   https://playwright.dev/docs/api/class-browser#browser-new-context-option-extra-http-headers
    #   https://playwright.dev/docs/api/class-browser#browser-new-page-option-extra-http-headers


@cli.command("web")
def web_cli():
    """Start HTTP server listen on :py:obj:`SIDECAR_LISTEN` host & port."""
    init()
    print(f"DEBUG: SideCar server listens on {SIDECAR_LISTEN}", file=sys.stderr)
    web.run(host=SIDECAR_LISTEN[0], port=SIDECAR_LISTEN[1], debug=False)


@web.route("/health", methods=["GET"])
def web_health():
    return flask.Response("OK", mimetype="text/plain")


@web.route("/sessions/get/<string:name>/<int:n>/", methods=["GET"])
def web_sessions_get(name: str, n: int):
    # example to request 3 sessions from google.com:
    #    http://127.0.0.2:50000/sessions/get/google.com/3/

    cls = MAP_JOB_TYPES.get(name)
    if cls is None:
        flask.abort(400, f"ERROR: session name '{name}' is unknow")

    t0 = timeit.default_timer()
    con = cls.from_browser(GLOBAL_BROWSER, n)
    t1 = timeit.default_timer()
    print(f"DEBUG: [{name}] job created {n} sessions in {t1-t0}", file=sys.stderr)

    return flask.Response(
        msgspec.json.encode(con).decode("utf-8"),
        mimetype="application/json",
    )


@cli.command("sessions.get")
def cli_sessions_get(
    name: Annotated[str, typer.Argument(help="name of the session type")],
    n: Annotated[int, typer.Option(help="number of sessions")] = 3,
    url: Annotated[str, typer.Option(help=f"request session from SearXNG's sidecar server (e.g. {SIDECAR_URL})")] = "",
    timeout: Annotated[int, typer.Option(help="timeout in sec.")] = 3,
):
    """Prints JSON encoded list of session data on stdout.  The JSON schema is
    of type :py:obj:`SessionContainer`.

    With the optionen ``url`` and ``timeout``, the session data can be requested
    from a remote source.
    """
    cls = MAP_JOB_TYPES.get(name)
    if cls is None:
        print(f"ERROR: session name '{name}' is unknow", file=sys.stderr)
        raise typer.Exit(42)
    t0 = timeit.default_timer()

    if url:
        print(f"DEBUG: SideCar server listens on {SIDECAR_LISTEN}", file=sys.stderr)
        job = cls.from_request(sidecar_url=SIDECAR_URL, n=n, timeout=timeout)
    else:
        try:
            init()
            job = cls.from_browser(GLOBAL_BROWSER, n)
        finally:
            GLOBAL_BROWSER.quit()

    t1 = timeit.default_timer()

    print(f"DEBUG: [{name}] job created {n} sessions in {t1-t0}", file=sys.stderr)
    if not job.ok:
        print(f"DEBUG: [{name}] job status isn't OK :-o", file=sys.stderr)
        for msg in job.messages:
            print(f"DEBUG: [{name}]  msg: {msg}", file=sys.stderr)

    print(
        msgspec.json.encode(job).decode("utf-8"),
        file=sys.stdout,
    )
