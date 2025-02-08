# SPDX-License-Identifier: AGPL-3.0-or-later
"""This module implements the type extensions applied by SearXNG.

- :py:obj:`flask.request` is replaced by :py:obj:`sxng_request`
- :py:obj:`flask.Request` is replaced by :py:obj:`SXNG_Request`
- :py:obj:`httpx.response` is replaced by :py:obj:`SXNG_Response`

----

.. py:attribute:: sxng_request
   :type: SXNG_Request

   A replacement for :py:obj:`flask.request` with type cast :py:obj:`SXNG_Request`.

.. autoclass:: SXNG_Request
   :members:

.. autoclass:: SXNG_Response
   :members:

"""
# pylint: disable=invalid-name
from __future__ import annotations

__all__ = ["SXNG_Request", "sxng_request", "SXNG_Response"]

import timeit
import typing

import flask
import httpx

if typing.TYPE_CHECKING:
    import searx.preferences
    import searx.results
    import searx.client


class SXNG_Request(flask.Request):
    """SearXNG extends the class :py:obj:`flask.Request` with properties from
    *this* class definition, see type cast :py:obj:`sxng_request`.
    """

    # FIXME .. should no longer be needed ..
    # req_plugins: list[str]
    # """List of plugin IDs (:py:obj:`searx.plugins.Plugin.id`) activated in the
    # request."""

    preferences: "searx.preferences.Preferences"
    """The prefernces of the request."""

    client: "searx.client.HTTPClient"
    """Instance of the HTTPClient."""

    errors: list[str]
    """A list of errors (translated text) added by :py:obj:`searx.webapp` in
    case of errors."""
    # request.form is of type werkzeug.datastructures.ImmutableMultiDict
    # form: dict[str, str]

    start_time: float
    """Start time of the request, :py:obj:`timeit.default_timer` added by
    :py:obj:`searx.webapp` to calculate the total time of the request."""

    render_time: float
    """Duration of the rendering, calculated and added by
    :py:obj:`searx.webapp`."""

    timings: list["searx.results.Timing"]
    """A list of :py:obj:`searx.results.Timing` of the engines, calculatid in
    and hold by :py:obj:`searx.results.ResultContainer.timings`."""

    form: dict[str, str]
    """flask.request.form_ is of type ImmutableMultiDict_, to merge GET, POST
    vars we need a (mutable) python dict.

    _flask.request.form:
        https://flask.palletsprojects.com/en/stable/api/#flask.Request.form
    _ImmutableMultiDict:
        https://werkzeug.palletsprojects.com/en/stable/datastructures/#werkzeug.datastructures.ImmutableMultiDict
    """

    @staticmethod
    def init(preferences: "searx.preferences.Preferences", client: "searx.client.HTTPClient"):
        sxng_request.preferences = preferences
        sxng_request.client = client
        sxng_request.start_time = timeit.default_timer()  # pylint: disable=assigning-non-slot
        sxng_request.render_time = 0  # pylint: disable=assigning-non-slot
        sxng_request.timings = []  # pylint: disable=assigning-non-slot
        sxng_request.errors = []  # pylint: disable=assigning-non-slot

        # merge GET, POST vars into request.form
        sxng_request.form = dict(sxng_request.form.items())  # type: ignore
        for k, v in sxng_request.args.items():
            if k not in sxng_request.form:
                sxng_request.form[k] = v


#: A replacement for :py:obj:`flask.request` with type cast :py:`SXNG_Request`.
sxng_request = typing.cast(SXNG_Request, flask.request)


class SXNG_Response(httpx.Response):
    """SearXNG extends the class :py:obj:`httpx.Response` with properties from
    *this* class (type cast of :py:obj:`httpx.Response`).

    .. code:: python

       response = httpx.get("https://example.org")
       response = typing.cast(SXNG_Response, response)
       if response.ok:
          ...
    """

    ok: bool
