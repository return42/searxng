# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!! [POC:SideCar]

In this POC, to use this command line, first jump into SerXNG's
developer environment:::

    $ ./manage dev.env

To get an overview of available commands:::

    (dev.env)$ python -m searx.sidecar --help
"""

__all__ = ["CACHE", "init_searxng"]

import flask

from searx import logger, get_setting
from .cache import CACHE
from .sessions import SESSIONS_CACHE_PUSH, sessions_cache_push

log = logger.getChild("sidecar")


def init_searxng(web_app: "flask.Flask") -> bool:
    if not get_setting("sidecar.auth_tokens"):
        log.warning("[POC] can't activate SideCar, missing sidecar.auth_tokens")
    else:
        log.info(f"[POC] add endpoint {SESSIONS_CACHE_PUSH} POST")
        web_app.add_url_rule(SESSIONS_CACHE_PUSH, view_func=sessions_cache_push, methods=["POST"])

    return True
