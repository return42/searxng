# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!   [POC:SideCar]

Implementation of a command line for SideCar's tools & services.

In this POC, to use this command line, first jump into SerXNG's
developer environment::

  $ ./manage dev.env

To get an overview of available commands::

  (dev.env)$ python -m searx.sidecar_pkg --help

----

To build up a simple scenario for [POC:SideCar] we use a (remote) SearXNG
developer instance ..

In the settings.yml add an entry::

    sidecar:
      auth_tokens: ["my-secret"]

Start a developer instance::

  $ make run

.. _#5286: https://github.com/searxng/searxng/issues/5286

While writing this POC, the google engine didn't work::

  !go foo

does not return any result (see _#5286).

The cause of this problem is that Google search has recently only been available
in a *verified* browser session, if the browser session is not verified by a
CAPTCHA challenge, google will not process the search request.

This POC comes with a command line to process the Google CAPTCHA challenge::

  (dev.env)$ python -m searx.sidecar_pkg sessions push google.com

  DEBUG: Wait for the user to solve the CAPTCHA
  ................
  DEBUG: delete cookies & clean localStorage -->['09ADiQh0cqO6...' ... ]<--
  DEBUG: [google.com] job created session in 21.276801308995346 sec
  DEBUG: send sessions to http://127.0.0.1:8888/sidecar/sessions/cache/push
  DEBUG: from http://127.0.0.1:8888/sidecar/sessions/cache/push got 'OK'

A web browser is then opened in which the user solves the challenge for the
Google CAPTCHA.  After that, the *verified* session is sent to the remote
SearXNG instance (default: http://127.0.0.1:8888/sidecar, use --help).

On the SearXNG instance, you can check the state of the cache::

  (dev.env)$ python -m searx.sidecar cache state
  ...
  cache tables and key/values
  ===========================
  [WebSession ] 2025-11-16 10:05:57 {"http_headers": .., "session_type":"google.com"} -->
  [WebSession ] 2025-11-16 10:59:18 {"http_headers": ..,"session_type":"startpage.com"} -->
  Number of contexts: 1
  number of key/value pairs: 2
  ..

Back in the search dialog of the SearXNG instance, retry ``!go foo`` and you
should now get some results.

-----

The scenario above is intended for development purpose, in a real scenario the
SearXNG instance is a remote and the command line runs on a local desktop.

.. _answer CAPTCHA from server’s IP:
    https://docs.searxng.org/admin/answer-captcha.html

To `answer CAPTCHA from server’s IP`_ open a SSH tunnel (SOCKS5 proxy)::

    # SOCKS server: socks://127.0.0.1:8080
    $ ssh -q -N -D 8080 user@example.org

To answer the CAPCHA and build/send the session object::

    $ python -m searx.sidecar_pkg sessions push \
          --searxng https://sxng.example.org/sidecar \
          --socks5 127.0.0.1:8080 \
          google.com

    INFO: WebSession will use proxy: 127.0.0.1:8080
    DEBUG: Wait for the user to solve the CAPTCHA
    ................
    DEBUG: delete cookies & clean localStorage -->[...]<--
    DEBUG: [google.com] job created session in 23.128173892007908 sec
    DEBUG: send sessions to https://sxng.example.org/sidecar/sessions/cache/push
    DEBUG: from https://sxng.example.org/sidecar/sessions/cache/push got 'OK'

----

    ToDo: set HTTP-headers

    - https://www.zenrows.com/blog/web-scraping-headers#common-http-headers
      request.headers["Accept-Language"] = "en"
    - to test headers, see response of: https://httpbin.io/headers

    ToDo: is Splinter_ the right tool?

    .. _Splinter: https://splinter.readthedocs.io/en/latest/
    .. _Selenium: https://www.selenium.dev/

    Except the User-Agent, Selenium_ (the browser driver from Splinter_)
    does not support to modify HTTP headers!

    Options:

    - Can we implement a JS script which is able to set HTTP headers in the
      outgoing request?

    - Alternative browser automation tool?

      - https://pydoll.tech/  (Chrom)
      - https://playwright.dev/python (cross browser!)
        - https://playwright.dev/python/docs/api/class-request#request-all-headers
        - https://playwright.dev/docs/api/class-browser#browser-new-context-option-extra-http-headers
        - https://playwright.dev/docs/api/class-browser#browser-new-page-option-extra-http-headers

"""
# pylint: disable=too-few-public-methods,disable=invalid-name

# - https://github.com/searxng/searxng/issues/5284
from __future__ import annotations
import sys

# msgspec: note that if using PEP 563 “postponed evaluation of annotations”
# (e.g. from __future__ import annotations) only the following spellings will
# work: https://jcristharif.com/msgspec/structs.html#class-variables
# from typing import ClassVar
import typing as t
import json

import timeit
from typing_extensions import Annotated

import flask
import httpx
import msgspec
import typer


from . import MAP_CONTAINER_TYPES
from .cfg import CFG
from .types import SessionType
from .web_session import WebContainer, WebSessionCtx, BROWSER

if t.TYPE_CHECKING:
    from splinter.driver.webdriver import BaseWebDriver  # type: ignore[reportMissingTypeStubs]

cli_web = typer.Typer(name="web", help="SideCar's web server.")
cli_sessions = typer.Typer(name="sessions", help="Manage engine sessions.")

WEB = flask.Flask("sidecar")
CLI = typer.Typer(epilog="")
CLI.add_typer(cli_web)
CLI.add_typer(cli_sessions)

GLOBAL_BROWSERS: "dict[tuple[str, bool], BaseWebDriver]" = {}


def get_browser(ctx: WebSessionCtx, headless: bool = False) -> "BaseWebDriver":
    # pylint: disable=import-outside-toplevel

    key = (BROWSER.ctx_id(ctx), headless)
    browser = GLOBAL_BROWSERS.get(key)
    if not browser:
        cls = MAP_CONTAINER_TYPES.get(ctx.session_type)
        if cls is None:
            raise ValueError(f"ERROR: session type '{ctx.session_type}' is not implemented")
        browser = cls.get_browser(
            user_agent=ctx.http_headers["user-agent"],
            socks5=CFG.SOCKS5,
            headless=headless,
        )
        GLOBAL_BROWSERS[key] = browser
    return browser


@cli_web.command("start", help=f"HTTP server listen on host {CFG.SIDECAR_LISTEN}")
def web_start():
    """Start HTTP server listen on :py:obj:`CFG.SIDECAR_LISTEN` host & port."""
    print(f"DEBUG: SideCar server listens on {CFG.SIDECAR_LISTEN}", file=sys.stderr)
    WEB.run(host=CFG.SIDECAR_LISTEN[0], port=CFG.SIDECAR_LISTEN[1], debug=False)


@WEB.route("/health", methods=["GET"])
def web_health():
    return flask.Response("OK", mimetype="text/plain")


@cli_sessions.command("push")
def cli_sessions_push(
    session_type: Annotated[SessionType, typer.Argument(help="name of the session type")],
    searxng: Annotated[str, typer.Option(help="remote SearXNG instance")] = CFG.SXNG_URL,
    timeout: Annotated[int, typer.Option(help="timeout in sec")] = 10,
    socks5: Annotated[str, typer.Option(help="socks proxy (e.g. '127.0.0.1:8080')")] = "",
):
    """Build a session and push it to a SearXNG instance."""

    if not CFG.SXNG_AUTH_TOKEN:
        raise ValueError("missing CFG.SXNG_AUTH_TOKEN")

    if socks5:
        print(f"INFO: WebSession will use proxy: {socks5}", file=sys.stderr)
        CFG.SOCKS5 = socks5

    cls = MAP_CONTAINER_TYPES.get(session_type)
    if cls is None:
        print(f"ERROR: session type '{session_type}' is not implemented", file=sys.stderr)
        raise typer.Exit(42)

    if issubclass(cls, WebContainer):
        ctx = WebSessionCtx(session_type=session_type, http_headers={})
        # sets ctx.js_required, see WebContainer.__post_init__
        cls.init_ctx(ctx)

    # elif issubclass(cls, MySession):
    #     ctx = MySession(session_type=session_type, http_headers={})

    else:
        print(f"ERROR: session type '{session_type}' is not implemented", file=sys.stderr)
        raise typer.Exit(42)

    t0 = timeit.default_timer()

    browser = get_browser(ctx=ctx, headless=False)
    try:
        con = cls.from_browser(browser=browser, ctx=ctx, n=1)
    finally:
        if not isinstance(browser, tuple):
            browser.quit()

    t1 = timeit.default_timer()

    print(f"DEBUG: [{session_type}] job created session in {t1-t0} sec", file=sys.stderr)
    if not con.ok:
        print(f"ERROR: [{session_type}] job status isn't OK :-o", file=sys.stderr)
        for msg in con.messages:
            print(f"DEBUG: [{session_type}]  msg: {msg}", file=sys.stderr)
        raise typer.Exit(42)

    # 1. create container obj (builtin types)
    _con: dict[str, t.Any] = msgspec.to_builtins(con)

    # 2. send obj to remote
    url = f"{searxng}/sessions/cache/push"  # ToDo: see searx/sidecar.py

    headers = {"Authorization": f"Bearer {CFG.SXNG_AUTH_TOKEN}", "User-Agent": "SearXNG SideCar"}
    print(f"DEBUG: send sessions to {url}", file=sys.stderr)
    try:
        resp = httpx.post(url, headers=headers, timeout=timeout, json=_con)
    except httpx.HTTPError as exc:
        print(f"ERROR: from {url} got: '{exc}'", file=sys.stderr)
        raise typer.Exit(42)

    print(f"DEBUG: from {url} got '{resp.text}'", file=sys.stderr)
    if resp.text != "OK":
        raise typer.Exit(42)


@cli_sessions.command("get")
def cli_sessions_get(
    session_type: Annotated[SessionType, typer.Argument(help="name of the session type")],
    n: Annotated[int, typer.Option(help="number of sessions")] = 1,
    url: Annotated[
        str, typer.Option(help=f"request session from SearXNG's sidecar server (e.g. {CFG.SIDECAR_URL})")
    ] = "",
    timeout: Annotated[int, typer.Option(help="timeout in sec.")] = 10,
    socks5: Annotated[str, typer.Option(help="socks proxy (e.g. '127.0.0.1:8080')")] = "",
):
    """Prints JSON encoded list of session data on stdout.  The JSON schema is
    of type :py:obj:`WebContainer`.

    With the options ``url`` and ``timeout``, the session data can be requested
    from a remote source.
    """
    if socks5:
        print(f"INFO: WebSession will use proxy: {socks5}", file=sys.stderr)
        CFG.SOCKS5 = socks5

    cls = MAP_CONTAINER_TYPES.get(session_type)
    if cls is None:
        print(f"ERROR: session type '{session_type}' is not implemented", file=sys.stderr)
        raise typer.Exit(42)

    ctx = WebSessionCtx(session_type=session_type, http_headers={})
    # sets ctx.js_required, see WebContainer.__post_init__
    cls.init_ctx(ctx)

    t0 = timeit.default_timer()

    if url:
        print(f"DEBUG: SideCar server listens on {CFG.SIDECAR_LISTEN}", file=sys.stderr)
        con = cls.from_url(
            sidecar_url=CFG.SIDECAR_URL,
            ctx=ctx,
            n=n,
            timeout=timeout,
        )

    else:
        browser = get_browser(ctx=ctx, headless=False)
        try:
            con = cls.from_browser(browser=browser, ctx=ctx, n=n)
        finally:
            try:
                browser.quit()
            except Exception:
                pass

    t1 = timeit.default_timer()

    print(f"DEBUG: [{session_type}] job created {n} sessions in {t1-t0} sec", file=sys.stderr)
    if not con.ok:
        print(f"ERROR: [{session_type}] job status isn't OK :-o", file=sys.stderr)
        for msg in con.messages:
            print(f"DEBUG: [{session_type}]  msg: {msg}", file=sys.stderr)

    _con: dict[str, t.Any] = msgspec.to_builtins(con)
    print(json.dumps(_con, sort_keys=True, indent=4), file=sys.stdout)


@WEB.route("/engine/WebContainer/from_browser/<int:n>", methods=["POST"])
def web_sessions_get(n: int):

    con: WebContainer = msgspec.json.decode(flask.request.get_data(), type=WebContainer)
    cls = MAP_CONTAINER_TYPES.get(con.ctx.session_type)
    if cls is None:
        flask.abort(400, f"ERROR: session type '{con.ctx.session_type}' is not implemented")

    t0 = timeit.default_timer()
    con = cls.from_browser(get_browser(con.ctx, headless=not con.ui), ctx=con.ctx, n=n)
    t1 = timeit.default_timer()
    print(f"DEBUG: [{con.ctx.session_type}] created {n} sessions in {t1-t0} sec", file=sys.stderr)

    return flask.Response(
        msgspec.json.encode(con).decode("utf-8"),
        mimetype="application/json",
    )
