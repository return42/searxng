# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!   [POC:SideCar]"""

import flask
import msgspec

from searx import logger
from searx.extended_types import sxng_request
from searx.sidecar_pkg.web_session import WebContainer

from .cfg import CFG
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

    if f"Bearer {CFG.SXNG_AUTH_TOKEN}" != sxng_request.headers.get("Authorization"):
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
