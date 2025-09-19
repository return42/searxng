# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, global-statement, too-few-public-methods
"""
A network stack for SearXNG's engines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In httpx_ and similar libraries, a client (also named session) contains a pool
of HTTP connections.  The client reuses these HTTP connections and automatically
recreates them when the server at the other end closes the connections.

Whatever the library, each HTTP client uses only one proxy (eventually none) and
only one local IP address.

.. _httpx: https://www.python-httpx.org/

The primary use case of SearXNG is an engine that sends one or more outgoing
HTTP requests.  The :ref:`outgoing <settings outgoing>` HTTP requests are
largely determined by the following variables:

outgoing IPs (:py:obj:`Network.local_addresses`) and proxies (:py:obj:`Network.proxies`):
  The admin can configure an engine to use multiple proxies or IP addresses:
  SearXNG sends the outgoing HTTP requests through these different proxies and
  IP-addresses on a rotational basis. Its important to note here: one HTTP
  client can still use only one proxy or IP.

engine timeout (:ref:`request_timeout <outgoing.request_timeout>`):
  When SearXNG executes an engine request, there is also a hard timeout: The
  total runtime of the engine must not exceed a certain value.  Its important to
  note here: the total runtime is largely determined by the HTTP requests.

:ref:`retries <outgoing.retries>` of a HTTP request:
  In addition, an engine can ask the SearXNG network to repeat a failed HTTP
  request one or more times. Its important to note here: the first request and
  all retries run in the same total runtime timeout.
"""

__all__ = [
    "Network",
    "get_network",
    "initialize",
    "verify_tor_proxy_works",
    "raise_for_httperror",
]

import typing as t

import asyncio
import threading
import concurrent.futures
from queue import SimpleQueue
from types import MethodType
from timeit import default_timer
from collections.abc import Iterable
from contextlib import contextmanager

import httpx
import anyio

from searx import logger
from searx.extended_types import SXNG_Response

from .network import get_network, initialize, verify_tor_proxy_works
from .client import get_loop
from .raise_for_httperror import raise_for_httperror
from .network import Network

logger = logger.getChild("network")


class RequestDescr(dict[str, t.Any]):
    """Request description for the multi_requests function

    .. code:: python

       url_list = [
           "https://example.org?q=foo",
           "https://example.org?q=bar",
       ]
       kwargs = {
           "allow_redirects": False,
           "headers": resp.search_params[""headers"],
       }
       request_list = [ RequestDescr("GET", u, **kwargs) for u in url_list ]
       response_list = multi_requests(request_list)

       for i, resp in enumerate(response_list):
           if not isinstance(redirect_response, Exception):
               print(f"{i} HTTP status: {resp.status}")
    """

    def __init__(self, method: str, url: str, kwargs: dict[str, t.Any]):
        super().__init__(kwargs)
        self["method"] = method
        self["url"] = url


@t.final
class NetworkLocals(threading.local):
    """`Thread local data`_

    FIXME: document for what purpose we use these thread local data!

    .. _Thread local data:
       https://docs.python.org/3/library/threading.html#thread-local-data
    """

    def __init__(
        self,
        timeout: float = 0,
        total_time: float = 0,
        start_time: float = 0,
        network: Network | None = None,
    ):
        self.timeout = timeout
        self.total_time = total_time
        self.start_time = start_time
        self.network = network


THREADLOCALS = NetworkLocals()


def reset_time_for_thread():
    """Sets thread's total time to 0."""
    logger.debug("[%s] reset THREADLOCALS.total_time=0", threading.current_thread().name)
    THREADLOCALS.total_time = 0


def get_time_for_thread() -> float:
    """Returns thread's total time."""
    return THREADLOCALS.total_time


def set_timeout_for_thread(timeout: float, start_time: float):
    logger.debug("[%s] set THREADLOCALS timeout=%s start_time=%s", timeout, start_time, threading.current_thread().name)
    THREADLOCALS.timeout = timeout
    THREADLOCALS.start_time = start_time


def set_context_network_name(network_name: str):
    logger.debug("[%s] set THREADLOCALS network='%s' (context)", threading.current_thread().name, network_name)
    THREADLOCALS.network = get_network(network_name)


def get_context_network() -> "Network":
    """Return thread's network object.  If unset, return value from
    :py:obj:`get_network`."""
    return THREADLOCALS.network or get_network()


def _get_timeout(start_time: float, kwargs: RequestDescr) -> float:

    timeout: float = kwargs.get("timeout") or THREADLOCALS.timeout
    # 2 minutes timeout for the requests without timeout
    timeout = timeout or 120
    # adjust actual timeout
    timeout += 0.2  # overhead
    if start_time:
        timeout -= default_timer() - start_time
    return timeout


@contextmanager
def _record_http_time():

    ctx_start = default_timer()
    try:
        yield THREADLOCALS.start_time or ctx_start
    finally:
        # update total_time.
        # See get_time_for_thread() and reset_time_for_thread()
        ctx_end = default_timer()
        THREADLOCALS.total_time += ctx_end - ctx_start


def request(request_desc: RequestDescr) -> SXNG_Response:
    """Sends an HTTP request (httpx.request_).


    .. _httpx.request: https://www.python-httpx.org/api/#helper-functions
    """

    network = get_context_network()

    with _record_http_time() as ctx_start_time:
        request_desc["timeout"] = request_desc.get("timeout") or THREADLOCALS.timeout
        ctx_timeout = _get_timeout(ctx_start_time, request_desc)
        logger.debug(
            "[%s] send HTTP request in network='%s' (context timeout: %s sec)",
            threading.current_thread().name,
            network.name,
            ctx_timeout,
        )

        future = asyncio.run_coroutine_threadsafe(network.call_client(**request_desc), get_loop())
        try:
            return future.result(ctx_timeout)
        except concurrent.futures.TimeoutError as e:
            raise httpx.TimeoutException('Timeout', request=None) from e


def multi_requests(request_list: list["RequestDescr"]) -> list[SXNG_Response | Exception]:
    """Send multiple HTTP requests in parallel. Wait for all requests to finish."""

    with _record_http_time() as ctx_start_time:
        # send the requests
        network = get_context_network()
        loop = get_loop()
        future_list: list[tuple[concurrent.futures.Future[SXNG_Response], float]] = []

        for request_desc in request_list:
            request_desc["timeout"] = request_desc.get("timeout") or THREADLOCALS.timeout
            ctx_timeout = _get_timeout(ctx_start_time, request_desc)
            future = asyncio.run_coroutine_threadsafe(network.request(**request_desc), loop)
            future_list.append((future, ctx_timeout))

        # read the responses
        responses: list[SXNG_Response | Exception] = []
        for future, timeout in future_list:
            try:
                resp = future.result(timeout)
                if resp:
                    responses.append(resp)
            except concurrent.futures.TimeoutError:
                responses.append(httpx.TimeoutException('Timeout', request=None))
            except Exception as e:  # pylint: disable=broad-except
                responses.append(e)
        return responses


def get(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP GET :py:obj:`request`"""
    return request(RequestDescr("get", url, kwargs))


def options(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP OPTIONS :py:obj:`request`"""
    return request(RequestDescr("options", url, kwargs))


def head(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP HEAD :py:obj:`request`"""
    return request(RequestDescr("head", url, kwargs))


def post(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP POST :py:obj:`request`"""
    return request(RequestDescr("post", url, kwargs))


def put(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP PUT :py:obj:`request`"""
    return request(RequestDescr("put", url, kwargs))


def patch(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP PATCH :py:obj:`request`"""
    return request(RequestDescr("patch", url, kwargs))


def delete(url: str, **kwargs: t.Any) -> SXNG_Response:
    """HTTP DELETE :py:obj:`request`"""
    return request(RequestDescr("delete", url, kwargs))


#  XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX


async def stream_chunk_to_queue(
    network: "Network",
    queue: SimpleQueue[httpx.Response | bytes | Exception | None],
    method: str,
    url: str,
    **kwargs: t.Any,
):
    try:
        async with await network.stream(method, url, **kwargs) as response:
            queue.put(response)
            # aiter_raw: access the raw bytes on the response without applying any HTTP content decoding
            # https://www.python-httpx.org/quickstart/#streaming-responses
            async for chunk in response.aiter_raw(65536):
                if len(chunk) > 0:
                    queue.put(chunk)
    except (httpx.StreamClosed, anyio.ClosedResourceError):
        # the response was queued before the exception.
        # the exception was raised on aiter_raw.
        # we do nothing here: in the finally block, None will be queued
        # so stream(method, url, **kwargs) generator can stop
        pass
    except Exception as e:  # pylint: disable=broad-except
        # broad except to avoid this scenario:
        # exception in network.stream(method, url, **kwargs)
        # -> the exception is not catch here
        # -> queue None (in finally)
        # -> the function below steam(method, url, **kwargs) has nothing to return
        queue.put(e)
    finally:
        queue.put(None)


def _stream_generator(method: str, url: str, **kwargs: t.Any):
    queue: SimpleQueue[httpx.Response | bytes | Exception | None] = SimpleQueue()
    network = get_context_network()
    future = asyncio.run_coroutine_threadsafe(
        stream_chunk_to_queue(
            network,
            queue,
            method,
            url,
            **kwargs,
        ),
        get_loop(),
    )

    # yield chunks
    obj_or_exception = queue.get()
    while obj_or_exception is not None:
        if isinstance(obj_or_exception, Exception):
            raise obj_or_exception
        yield obj_or_exception
        obj_or_exception = queue.get()
    future.result()


def _close_response_method(resp: httpx.Response) -> None:
    asyncio.run_coroutine_threadsafe(resp.aclose(), get_loop())
    # reach the end of _self.generator ( _stream_generator ) to an avoid memory leak.
    # it makes sure that :
    # * the httpx response is closed (see the stream_chunk_to_queue function)
    # * to call future.result() in _stream_generator
    for _ in resp._generator:  # pylint: disable=protected-access
        continue


def stream(method: str, url: str, **kwargs: t.Any) -> tuple[httpx.Response, Iterable[bytes]]:
    """Replace httpx.stream.

    Usage:
    response, stream = poolrequests.stream(...)
    for chunk in stream:
        ...

    httpx.Client.stream requires to write the httpx.HTTPTransport version of the
    the httpx.AsyncHTTPTransport declared above.
    """
    generator = _stream_generator(method, url, **kwargs)

    # FIXME
    import pdb

    pdb.set_trace()

    # yield response
    response: httpx.Response = next(generator)  # pylint: disable=stop-iteration-return
    if isinstance(response, Exception):
        raise response

    response._generator = generator  # pylint: disable=protected-access
    response.close = MethodType(_close_response_method, response)

    return response, generator
