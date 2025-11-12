# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!   [POC:SideCar]"""

import flask
import msgspec

from searx import logger, get_setting
from searx.extended_types import sxng_request
from searx.sidecar_pkg.web_session import WebContainer

from .cache import CACHE

# REST API endpoints ..

SESSIONS_CACHE_PUSH = "/sidecar/sessions/cache/push"
log = logger.getChild("sidecar")


def sessions_cache_push():
    """Endpoint to push sessions to SideCar's cache in SearXNG.

    ToDo: auth needs more work!!

    hardening? -> The maximum POST request body size is configured on the HTTP
    server and typically ranges from 1MB to 2GB.
    """
    http_auth = sxng_request.headers.get("Authorization")
    if not http_auth:
        log.error(f"[POC] request {SESSIONS_CACHE_PUSH} missed HTTP Authorization")
        flask.abort(401)

    auth_ok = False
    for token in get_setting("sidecar.auth_tokens", []):
        if f"Bearer {token}" != http_auth:
            continue
        auth_ok = True
        break

    if not auth_ok:
        log.error(f"[POC] request {SESSIONS_CACHE_PUSH} does not have a valid token")
        flask.abort(401)

    try:
        con: WebContainer = msgspec.json.decode(sxng_request.get_data(), type=WebContainer)
        for session in con.sessions:
            CACHE.session_push(session=session)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # ToDo ..
        log.error(f"[POC] request {SESSIONS_CACHE_PUSH} fails: {exc}")
        flask.abort(500)
    return "OK"
