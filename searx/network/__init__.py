# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
# pyright: basic
# pylint: disable=redefined-outer-name
# ^^ because there is the raise_for_httperror function and the raise_for_httperror parameter.
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

outgoing IPs (:ref:`source_ips <outgoing.source_ips>`) and :ref:`proxies <outgoing.proxies>`:
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

However, we want to keep the engine code simple and keep the complexity either
in the configuration or the core components (here in SearXNG's network stack).
To answer the above requirements, the :py:obj:`searx.network` module introduces
three components:

- :py:obj:`.client.HTTPClient` and :py:obj:`.client.TorHTTPClient` are two
  classes that wrap one or multiple httpx.Client_

- :py:obj:`.context.NetworkContext` to provide a runtime context for the
  engines.  The constructor needs a global timeout and an HTTPClient factory.
  :py:obj:`.context.NetworkContext` is an abstract class with three
  implementations, one for each retry policy.

  - :py:obj:`context.NetworkContextRetryFunction`
  - :py:obj:`context.NetworkContextRetrySameHTTPClient`
  - :py:obj:`context.NetworkContextRetryDifferentHTTPClient`

- :py:obj:`.network.NetworkManager`, the global instance of this manager is
  :py:obj:`.network.NETWORKS` where each network:

  - holds the configuration defined in settings.yml

  - creates :py:obj:`context.NetworkContext` fed with a
    :py:obj:`client.HTTPClient` or :py:obj:`client.TorHTTPClient`.  This is
    where the rotation between the proxies and IP addresses happens.

.. _network examples:

Network Context & Request
~~~~~~~~~~~~~~~~~~~~~~~~~

Two helpers set a :py:obj:`context.NetworkContext`:

- The context manager :py:obj:`networkcontext_manager`, for the generic use
  case.

- The decorator :py:obj:`networkcontext_decorator`, the intended usage is an
  external script (see :ref:`searxng_extra`).

.. tabs::

  .. group-tab:: networkcontext_manager

     .. code:: python

        from searx import network
        from time import sleep

        def net_time(timezone):
            return network.get(f'https://worldtimeapi.org/api/timezone/{timezone}').json()

        with network.networkcontext_manager('worldtime', timeout=3.0) as net_ctx:
            sleep(1) # there are 2 sec left for the function call ..
            json_response = net_ctx.call(net_time, 'GMT')
            print(json_response)

        print("End of network-context")

  .. group-tab:: networkcontext_decorator

     .. code:: python

        from searx import network
        from time import sleep

        @network.networkcontext_decorator('ifconfig', timeout=3.0)
        def main()
            sleep(1) # there are 2 sec left for the function call ..
            my_ip = network.get("https://ifconfig.me/ip").text
            print(my_ip)

       if __name__ == '__main__':
           main()


In both examples above the :py:obj:`get` function is used to send a HTTP ``GET``
request, alternatively :py:obj:`post` can be used to send a HTTP ``POST``
request.  Both functions are simply wrapper around the central HTTP
:py:obj:`network.request <request>` function.

.. hint::

   A HTTP :py:obj:`network.request <request>` can only be called in a
   :py:obj:`context.NetworkContext`, otherwise SearXNG raises a
   :py:obj:`NetworkContextNotFound` exception!

   - HTTP ``GET`` :py:obj:`get`
   - HTTP ``POST`` :py:obj:`post`
   - HTTP ``PUT`` :py:obj:`put`
   - HTTP ``PATCH`` :py:obj:`patch`
   - HTTP ``DELETE`` :py:obj:`delete`
   - HTTP ``OPTIONS`` :py:obj:`options`
   - HTTP ``HEAD`` :py:obj:`head`


Architecture
~~~~~~~~~~~~

The overall architecture:

:py:obj:`searx.network.network.NETWORKS`:
  Contains all the networks

  .. code:: python

     NETWORKS = NetworkManager()

  The method :py:obj:`NETWORKS.get('network_name') <network.NetworkManager.get>`
  returns an initialized Network named ``network_name``.  As long as no value is
  specified for engine's :ref:`engine network` in the engine setup, SearXNG
  creates a new network for each :ref:`engine name`.

:py:obj:`searx.network.network.Network`:
  Defines a network (a set of proxies, local IP address, etc...).

  - The *networks* are defined in ``settings.yml`` / the global defaults are
    defined in the :ref:`outgoing <settings outgoing>` settings.

  - The method :py:obj:`network.Network.get_context` creates a new
    :py:obj:`context.NetworkContext`.  However, this context will not usually be
    created directly, usually the decorator or the ``with`` context will be
    used, which then sets up the context.

    .. code:: python

       network = NETWORKS.get(network_name)
       network_context = network.get_context(timeout=timeout, start_time=start_time)

:py:obj:`searx.network.context`:
  Contains three different implementations of
  :py:obj:`context.NetworkContext`. One for each retry policy.

:py:obj:`searx.network.client`:
  :py:obj:`client.HTTPClient` and :py:obj:`client.TorHTTPClient` implement
  wrappers around httpx.Client_.

Threads
~~~~~~~

Within the same thread, the caller can use :py:obj:`network.request <request>`
and similar functions without worrying about the HTTP client through which the
HTTP request is sent.  However, if the caller creates a new thread, it must
initialize a new :py:obj:`searx.network.context.NetworkContext`.

.. todo::

   A :py:obj:`context.NetworkContext` is most probably thread-safe, but this
   has not been tested.

.. _httpx.Client: https://www.python-httpx.org/api/#client

API ``searx.network``
~~~~~~~~~~~~~~~~~~~~~

"""
import threading
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional, Union

import httpx

from searx.network.client import NOTSET, _NotSetClass
from searx.network.context import NetworkContext, P, R
from searx.network.network import NETWORKS
from searx.network.raise_for_httperror import raise_for_httperror

__all__ = [
    "NETWORKS",
    "NetworkContextNotFound",
    "networkcontext_manager",
    "networkcontext_decorator",
    "raise_for_httperror",
    "request",
    "get",
    "options",
    "head",
    "post",
    "put",
    "patch",
    "delete",
]


_THREADLOCAL = threading.local()
"""Thread-local that contains only one field: ``network_context``.
"""

_NETWORK_CONTEXT_KEY = 'network_context'
"""Key to access :py:obj:`_THREADLOCAL`"""

DEFAULT_MAX_REDIRECTS = httpx._config.DEFAULT_MAX_REDIRECTS  # pylint: disable=protected-access


class NetworkContextNotFound(Exception):
    """Exception, a :py:obj:`context.NetworkContext` is expected to exist for
    the current network request.  Use :py:obj:`networkcontext_decorator` or
    :py:obj:`networkcontext_manager` to set a :py:obj:`NetworkContext`

    """


@contextmanager
def networkcontext_manager(
    network_name: Optional[str] = None,
    timeout: Optional[float] = None,
    start_time: Optional[float] = None,
):
    """Python (:keyword:`with`) context manager for network requests in a
    :py:obj:`context.NetworkContext`.  The arguments of the
    :py:obj:`contextlib.contextmanager` are analogous to
    :py:obj:`networkcontext_decorator`, a description can be found there and a
    example usage is shown in :ref:`network examples`.  The yielded
    :py:obj:`context.NetworkContext` instance is *thread local*.

    """
    network = NETWORKS.get(network_name)
    network_context = network.get_context(timeout=timeout, start_time=start_time)
    setattr(_THREADLOCAL, _NETWORK_CONTEXT_KEY, network_context)
    try:
        yield network_context
    finally:
        delattr(_THREADLOCAL, _NETWORK_CONTEXT_KEY)
        del network_context


def networkcontext_decorator(
    network_name: Optional[str] = None, timeout: Optional[float] = None, start_time: Optional[float] = None
):
    """A :external:term:`decorator` (aka *wrapper function*) to set a
    :py:obj:`context.NetworkContext` for network requests in the *decorated*
    function. A example usage is shown in :ref:`network examples`.

    :param timeout: The timeout (in sec) is for the whole function and is infinite
        by default (``None``).  The timeout is counted from the current time or
        ``start_time`` if different from ``None``.

    :param start_time: The start time (*offset in sec from now*) of the
      timeout. The remaining time is calculated in
      :py:obj:`context.NetworkContext.get_remaining_time`.

    :param network_name: Name of the network for which the context is created.

    The global :py:obj:`.network.NETWORKS` manager serves networks according to
    their ``network_name``.  In the case of the engines, the networks to the
    engines (:ref:`engine network`) are managed here. For example, there is a
    network named ``google`` for the google engine, the context for this would
    be built roughly as follows:

    .. tabs::

       .. group-tab:: exemplary

          .. code:: python

             google_net = NETWORKS.get('google')
             google_net_context = google_net.get_context(timeout, start_time)
             resp = network.get("https://google.com/...")


       .. group-tab:: @networkcontext_decorator

          .. code:: python

             @networkcontext_decorator('google', timeout=3.0)
             def main()
                 resp = network.get("https://google.com/...")
                 ...

    """

    def func_outer(func: Callable[P, R]):
        @wraps(func)
        def func_inner(*args: P.args, **kwargs: P.kwargs) -> R:
            with networkcontext_manager(network_name, timeout, start_time) as network_context:
                return network_context.call(func, *args, **kwargs)

        return func_inner

    return func_outer


def request(
    method: str,
    url: str,
    params: Optional[httpx._types.QueryParamTypes] = None,
    content: Optional[httpx._types.RequestContent] = None,
    data: Optional[httpx._types.RequestData] = None,
    files: Optional[httpx._types.RequestFiles] = None,
    json: Optional[Any] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    timeout: httpx._types.TimeoutTypes = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """HTTP request in the *network stack*

    This function requires a :py:obj`NetworkContext` provided by either
    :py:obj:`networkcontext_decorator` or :py:obj:`networkcontext_manager`.  The
    implementation uses one or more httpx.Client_

    A HTTP request in the *network stack* is similar to httpx.request_ with some
    differences:

    ``proxies``:
      Is not available and has to be defined in the Network configuration
      (:ref:`proxies <outgoing.proxies>`).

    ``cert``:
        Is not available and is always ``None``.

    ``trust_env``:
        it is not available and is always ``True``.

    ``timeout``:
        The implementation uses the lowest timeout between this parameter and
        remaining time for the :py:obj:`context.NetworkContext`.

    ``allow_redirects``:
       Replaces the ``follow_redirects`` parameter to be compatible with the
       requests API.

    ``raise_for_httperror``:
        When ``True``, this function calls
        :py:obj:`searx.network.raise_for_httperror.raise_for_httperror`.

    Some parameters from httpx.Client_ are available:

    ``max_redirects``:
        Set to ``None`` to use the value from the Network configuration.  The
        maximum number of redirect responses that should be followed.

    ``verify``:
        Set to ``None`` to use the value from the :py:obj:`network.NetworkSettings`.

    ``limits``:
        Has to be defined in the :py:obj:`network.NetworkSettings` /
        compare `httpx pool limits`_.  :py:obj:`httpx.Limits`:

        - ``max_connections`` / :ref:`outgoing.pool_connections`
        - ``max_keepalive_connections`` / :ref:`outgoing.pool_maxsize`
        - ``keepalive_expiry`` / :ref:`outgoing.keepalive_expiry`

    ``default_encoding``:
        This parameter is not available and is always ``utf-8``.

    .. _httpx.request: https://www.python-httpx.org/api/#client
    .. _httpx pool limits: https://www.python-httpx.org/advanced/#pool-limit-configuration

    """
    # pylint: disable=too-many-arguments
    network_context: Optional[NetworkContext] = getattr(_THREADLOCAL, _NETWORK_CONTEXT_KEY, None)
    if network_context is None:
        raise NetworkContextNotFound()
    http_client = network_context._get_http_client()  # pylint: disable=protected-access
    return http_client.request(
        method,
        url,
        params=params,
        content=content,
        data=data,
        files=files,
        json=json,
        headers=headers,
        cookies=cookies,
        auth=auth,
        timeout=timeout,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        raise_for_httperror=raise_for_httperror,
    )


def get(
    url: str,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = True,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.get, see the request method for the details.

    allow_redirects is by default True (httpx default value is False).
    """
    # pylint: disable=too-many-arguments
    return request(
        "GET",
        url,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )


def options(
    url: str,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.options, see the request method for the details."""
    # pylint: disable=too-many-arguments
    return request(
        "OPTIONS",
        url,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )


def head(
    url: str,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.head, see the request method for the details."""
    # pylint: disable=too-many-arguments
    return request(
        "HEAD",
        url,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )


def post(
    url: str,
    content: Optional[httpx._types.RequestContent] = None,
    data: Optional[httpx._types.RequestData] = None,
    files: Optional[httpx._types.RequestFiles] = None,
    json: Optional[Any] = None,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.post, see the request method for the details."""
    # pylint: disable=too-many-arguments
    return request(
        "POST",
        url,
        content=content,
        data=data,
        files=files,
        json=json,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )


def put(
    url: str,
    content: Optional[httpx._types.RequestContent] = None,
    data: Optional[httpx._types.RequestData] = None,
    files: Optional[httpx._types.RequestFiles] = None,
    json: Optional[Any] = None,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.put, see the request method for the details."""
    # pylint: disable=too-many-arguments
    return request(
        "PUT",
        url,
        content=content,
        data=data,
        files=files,
        json=json,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )


def patch(
    url: str,
    content: Optional[httpx._types.RequestContent] = None,
    data: Optional[httpx._types.RequestData] = None,
    files: Optional[httpx._types.RequestFiles] = None,
    json: Optional[Any] = None,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.patch, see the request method for the details."""
    # pylint: disable=too-many-arguments
    return request(
        "PATCH",
        url,
        content=content,
        data=data,
        files=files,
        json=json,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )


def delete(
    url: str,
    params: Optional[httpx._types.QueryParamTypes] = None,
    headers: Optional[httpx._types.HeaderTypes] = None,
    cookies: Optional[httpx._types.CookieTypes] = None,
    auth: Optional[httpx._types.AuthTypes] = None,
    allow_redirects: bool = False,
    max_redirects: Union[_NotSetClass, int] = NOTSET,
    verify: Union[_NotSetClass, httpx._types.VerifyTypes] = NOTSET,
    timeout: httpx._types.TimeoutTypes = None,
    raise_for_httperror: bool = False,
) -> httpx.Response:
    """Similar to httpx.delete, see the request method for the details."""
    # pylint: disable=too-many-arguments
    return request(
        "DELETE",
        url,
        params=params,
        headers=headers,
        cookies=cookies,
        auth=auth,
        allow_redirects=allow_redirects,
        max_redirects=max_redirects,
        verify=verify,
        timeout=timeout,
        raise_for_httperror=raise_for_httperror,
    )
