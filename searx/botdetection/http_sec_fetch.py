# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Method ``http_sec_fetch``
-------------------------

The ``http_sec_fetch`` method protect resources from web attacks with `Fetch
Metadata`_.  A request is filtered out in case of:

- http header Sec-Fetch-Mode_ is invalid
- http header Sec-Fetch-Dest_ is invalid

.. _Fetch Metadata:
   https://developer.mozilla.org/en-US/docs/Glossary/Fetch_metadata_request_header

.. Sec-Fetch-Dest:
   https://developer.mozilla.org/en-US/docs/Web/API/Request/destination

.. Sec-Fetch-Mode:
   https://developer.mozilla.org/en-US/docs/Web/API/Request/mode


"""
# pylint: disable=unused-argument

from __future__ import annotations
from ipaddress import (
    IPv4Network,
    IPv6Network,
)

import flask
import werkzeug

from searx.extended_types import SXNG_Request

from . import config
from ._helpers import logger


def filter_request(
    network: IPv4Network | IPv6Network,
    request: SXNG_Request,
    cfg: config.Config,
) -> werkzeug.Response | None:

    val = request.headers.get("Sec-Fetch-Mode", "")
    if val != "navigate":
        logger.debug("invalid Sec-Fetch-Mode '%s'", val)
        return flask.redirect(flask.url_for('index'), code=302)

    val = request.headers.get("Sec-Fetch-Site", "")
    if val not in ('same-origin', 'same-site', 'none'):
        logger.debug("invalid Sec-Fetch-Site '%s'", val)
        flask.redirect(flask.url_for('index'), code=302)

    val = request.headers.get("Sec-Fetch-Dest", "")
    if val != "document":
        logger.debug("invalid Sec-Fetch-Dest '%s'", val)
        flask.redirect(flask.url_for('index'), code=302)

    return None
