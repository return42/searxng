# SPDX-License-Identifier: AGPL-3.0-or-later
"""This module implements some of the type extensions applied by SearXNG.

"""
# pylint: disable=invalid-name
from __future__ import annotations
import typing

import flask
import httpx

if typing.TYPE_CHECKING:
    import searx.preferences
    import searx.results


class SXNG_Request(flask.Request):
    """This class is never initialized and only used for type checking / type
    cast of :py:obj:`flask.Request`."""

    user_plugins: list[str]
    """list of searx.plugins.Plugin.id (the id of the plugins)"""

    preferences: "searx.preferences.Preferences"
    errors: list[str]
    # form: dict[str, str]
    start_time: float
    render_time: float
    timings: list["searx.results.Timing"]


sxng_request = typing.cast(SXNG_Request, flask.request)


class SXNG_Response(httpx.Response):
    """This class is never initialized and only used for type checking / type
    cast of :py:obj:`httpx.Response`."""

    ok: bool
