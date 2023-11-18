# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
# pyright: basic
"""This module implements various :py:obj:`NetworkContext` which deals with

- retry strategies: what to do when an HTTP request fails and retries>0
- record HTTP runtime
- timeout: In engines, the user query starts at one point in time, the engine
  timeout is the starting point plus a defined value.  NetworkContext sends HTTP
  requests following the request timeout and the engine timeouts.

Example of usage:

.. code:: python

   context = NetworkContextRetryFunction(...)  # or another implementation

   def my_engine():
       http_client = context.get_http_client()
       ip_ifconfig = http_client.request("GET", "https://ifconfig.me/")
       print("ip from ifconfig.me ", ip_ifconfig)
       ip_myip = http_client.request("GET", "https://api.myip.com").json()["ip"]
       print("ip from api.myip.com", ip_myip)
       assert ip_ifconfig == ip_myip
       # ^^ always true with NetworkContextRetryFunction and NetworkContextRetrySameHTTPClient

   result = context.call(my_engine)
   print('HTTP runtime:', context.get_total_time())

Note in the code above :py:obj:`NetworkContextRetryFunction` is instanced
directly for the sake of simplicity.  A ``NetworkContext`` are actually
instanciated using :py:obj:`network.Network.get_context`.  The default strategy
is :py:obj:`DIFFERENT_HTTP_CLIENT <NetworkContextRetryDifferentHTTPClient>`.

Various implementations define what to do when there is an exception in the
function ``my_engine``:

- :py:obj:`NetworkContextRetryFunction` gets another HTTP client and tries the
  whole function again.

- :py:obj:`NetworkContextRetryDifferentHTTPClient` gets another HTTP client and
  tries the query again.

- :py:obj:`NetworkContextRetrySameHTTPClient` tries the query again with the
  same HTTP client.

.. autoclasstree:: searx.network.context
   :namespace: searx.network.context
   :zoom:

"""
import functools
import ssl
from abc import ABC, abstractmethod
from contextlib import contextmanager
from timeit import default_timer
from typing import Callable, Optional, final

try:
    from typing import ParamSpec, TypeVar
except ImportError:
    # to support Python < 3.10
    from typing_extensions import ParamSpec, TypeVar

import httpx

from searx.network.client import ABCHTTPClient, SoftRetryHTTPException

P = ParamSpec('P')
R = TypeVar('R')
HTTPCLIENTFACTORY = Callable[[], ABCHTTPClient]

DEFAULT_TIMEOUT = 120.0
"""Default timeout used in a network context"""


class NetworkContext(ABC):
    """Abstract implementation of a network context.  The network context is the
    construct with which the retry strategies are implemented
    (:py:obj:`network.RetryStrategy`).  Instances of context are created by the
    method :py:obj:`network.Network._get_context`."""


    __slots__ = ('_retries', '_http_client_factory', '_http_client', '_start_time', '_http_time', '_timeout')

    def __init__(
        self,
        retries: int,
        http_client_factory: HTTPCLIENTFACTORY,
        start_time: Optional[float],
        timeout: Optional[float],
    ):
        """For a desscription of the arguments see :ref:`network examples` and
        :py:obj:`searx.network.networkcontext_decorator`."""


        self._retries: int = retries
        # wrap http_client_factory here, so we can forget about this wrapping
        self._http_client_factory = _TimeHTTPClientWrapper.wrap_factory(http_client_factory, self)
        self._http_client: Optional[ABCHTTPClient] = None
        self._start_time: float = start_time or default_timer()
        self._http_time: float = 0.0
        self._timeout: Optional[float] = timeout or DEFAULT_TIMEOUT

    @abstractmethod
    def call(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        """*Call* ``func`` within the network context.  This method must be
        implemented by the inheriting classes -- by the retry strategies.  In
        short: the implementation of this method IS the retry policy.

        The retry policy might:

        - returns the result of ``func`` call

        - call ``func`` multiple times and then return the result or ..

        - return a :py:obj:`SoftRetryHTTPException`

        - raise an :py:obj:`ssl.SSLError`, :py:obj:`httpx.RequestError` or
          :py:obj:`httpx.HTTPStatusError` exception when max retries has been
          reached.

        - raise an :py:obj:`httpx.TimeoutException` when max timeout of the
          context has been reached (:py:obj:`self.get_remaining_time`).

        Within the ``call`` method (within the retry strategy) a HTTP client can
        be set by :py:obj:`self._set_http_client`.  This client will be used
        fore instance in :py:obj:`searx.network.get`:

        .. code:: python

           from searx import network

           def net_time(timezone):

               # this HTTP "get" will use the HTTP client set by the retry
               # strategy in the network context, which is largely determined by
               # the settings and in which the retry strategy was also set.

               return network.get(f'https://worldtimeapi.org/api/timezone/{timezone}').json()

           with network.networkcontext_manager('worldtime', timeout=3.0) as net_ctx:
               json_response = net_ctx.call(net_time, 'GMT')
           print(json_response)

        """

    @final
    def request(self, *args, **kwargs):
        """Convenient method to wrap a call to *HTTP request* inside the the
        ``call`` method (within the retry strategy).

        Sets a new HTTP client (:py:obj:`self._set_http_client`) before passing
        the *HTTP request* to the :py:obj:`self.call` method."""

        self._set_http_client()
        return self.call(self._get_http_client().request, *args, **kwargs)

    @final
    def stream(self, *args, **kwargs):
        """Convenient method to wrap a call to *HTTP stream* inside the the
        ``call`` method (within the retry strategy).

        Sets a new HTTP client (:py:obj:`self._set_http_client`) before passing
        the *HTTP send* to the :py:obj:`self.call` method.

        .. code:: python

           network_context = NETWORKS.get('image_proxy').get_context()
           resp = network_context.stream(method='GET', url=url ..., timeout=30)

        """
        self._set_http_client()
        return self.call(self._get_http_client().stream, *args, **kwargs)

    @final
    def get_http_runtime(self) -> Optional[float]:
        """Return the amount of time spent on the HTTP requests (inside the
        ``call`` method).  Compare :py:obj:`record_http_time` and
        :py:obj:`_TimeHTTPClientWrapper.send`"""
        return self._http_time

    @final
    def get_remaining_time(self, _override_timeout: Optional[float] = None) -> float:
        """Return the remaining time for the context.  Takes into account the
        offset resulting from the ``start_time``. ``_override_timeout`` is not
        intended to be used outside this module.

        .. todo::

           Why does this functions adds a offset of ``timeout += 0.2``, is the
           value of 0.2 seconds arbitrary, how can this value be explained?

        """

        timeout = _override_timeout or self._timeout
        timeout += 0.2
        timeout -= default_timer() - self._start_time
        return timeout

    @final
    def _get_http_client(self) -> ABCHTTPClient:
        """Return the HTTP client to use for this context."""
        if self._http_client is None:
            raise ValueError("HTTP client has not been set")
        return self._http_client

    @final
    def _set_http_client(self):
        """Ask the NetworkContext to use another HTTP client using the factory.

        Use the method _get_new_client_from_factory() to call the factory,
        so the NetworkContext implementations can wrap the ABCHTTPClient.
        """
        self._http_client = self._get_new_client_from_factory()

    @final
    def _reset_http_client(self):
        self._http_client = None

    def _get_new_client_from_factory(self):
        return self._http_client_factory()

    @contextmanager
    def _record_http_time(self):
        """This decorator records the code's runtime and adds it to self.total_time"""
        time_before_request = default_timer()
        try:
            yield
        finally:
            self._http_time += default_timer() - time_before_request

    def __repr__(self):
        common_attributes = (
            f"{self.__class__.__name__}"
            + f" retries={self._retries!r} timeout={self._timeout!r} http_client={self._http_client!r}"
        )
        # get the original factory : see the __init__ method of this class and _TimeHTTPClientWrapper.wrap_factory
        factory = self._http_client_factory.__wrapped__
        # break the abstraction safely: get back the Network object through the bound method
        # see Network.get_context
        bound_instance = getattr(factory, "__self__", None)
        if bound_instance is not None and hasattr(bound_instance, 'get_context'):
            # bound_instance has a "get_context" attribute: this is most likely a Network
            # searx.network.network.Network is not imported to avoid circular import
            return f"<{common_attributes} network_context={factory.__self__!r}>"
        # fallback : this instance was not created using Network.get_context
        return f"<{common_attributes} http_client_factory={factory!r}>"


class _TimeHTTPClientWrapper(ABCHTTPClient):
    """Wrap an :py:obj:`ABCHTTPClient` to measure time and deal with timeout to
    make sure the total time does not exceed the timeout set on the
    NetworkContext"""

    __slots__ = ('http_client', 'network_context')

    @classmethod
    def wrap_factory(cls, network_context: NetworkContext):
        """Return a factory which wraps the result of
        :py::obj:`.network.Network.get_http_client` with
        :py::obj:`_TimeHTTPClientWrapper` instance."""

        def wrapped_factory():
            return _TimeHTTPClientWrapper(http_client_factory(), network_context)

        wrapped_factory.__wrapped__ = http_client_factory
        return wrapped_factory

    def __init__(self, http_client: ABCHTTPClient, network_context: NetworkContext) -> None:
        self.http_client = http_client
        self.network_context = network_context

    def send(self, stream, method, url, **kwargs) -> httpx.Response:
        """Send the HTTP request using :py:obj:`self.http_client`.  The
        remaining timeout for the HTTP request is calculated
        :py:obj:`NetworkContext.get_remaining_time`.  The time taken by the HTTP
        request is recorded by the :key:`with` context manager
        :py:obj:`NetworkContext.record_http_time`.

        .. todo::

           Inaccurate with stream: the method must record HTTP time with the
           close method of httpx.Response.  It is not a problem since stream are
           used only for the image proxy.

        """
        with self.network_context._record_http_time():  # pylint: disable=protected-access
            timeout = self._extract_timeout(kwargs)
            return self.http_client.send(stream, method, url, timeout=timeout, **kwargs)

    def close(self):
        return self.http_client.close()

    @property
    def is_closed(self) -> bool:
        return self.http_client.is_closed

    def _extract_timeout(self, kwargs):
        """Extract the timeout parameter and adjust it according to the
        remaining time"""
        timeout = kwargs.pop('timeout', None)
        return self.network_context.get_remaining_time(timeout)


class NetworkContextRetryFunction(NetworkContext):
    """When an HTTP request fails, this NetworkContext tries again
    the whole function with another HTTP client.

    This guarantees that func has the same HTTP client all along.
    """

    def call(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            # if retries == 1, this method can call `func` twice,
            # so the exit condition is self._retries must be equal or above zero
            # to allow two iteration
            while self._retries >= 0 and self.get_remaining_time() > 0:
                self._set_http_client()
                try:
                    return func(*args, **kwargs)  # type: ignore
                except SoftRetryHTTPException as e:
                    if self._retries <= 0:
                        return e.response
                except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as e:
                    if self._retries <= 1:
                        # raise the exception only there is no more try
                        raise e
                self._retries -= 1
            if self.get_remaining_time() <= 0:
                raise httpx.TimeoutException("Timeout")
            raise httpx.HTTPError("Internal error: this should not happen")
        finally:
            self._reset_http_client()

    def _get_new_client_from_factory(self):
        return _RetryFunctionHTTPClient(super()._get_new_client_from_factory(), self)


class _RetryFunctionHTTPClient(ABCHTTPClient):
    """Companion class of NetworkContextRetryFunction

    Do one thing: if the retries count of the NetworkContext is zero and there is a SoftRetryHTTPException,
    then the send method catch this exception and returns the HTTP response.
    This make sure the SoftRetryHTTPException exception is not seen outside the searx.network module.
    """

    def __init__(self, http_client: ABCHTTPClient, network_context: NetworkContextRetryFunction):
        self.http_client = http_client
        self.network_context = network_context

    def send(self, stream: bool, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return self.http_client.send(stream, method, url, **kwargs)
        except SoftRetryHTTPException as e:
            if self.network_context._retries <= 0:  # pylint: disable=protected-access
                return e.response
            raise e

    def close(self):
        return self.http_client.close()

    @property
    def is_closed(self) -> bool:
        return self.http_client.is_closed


class NetworkContextRetrySameHTTPClient(NetworkContext):
    """When an HTTP request fails, this NetworkContext tries again
    the same HTTP request with the same HTTP client

    The implementation wraps the provided ABCHTTPClient with _RetrySameHTTPClient."""

    def call(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            self._set_http_client()
            return func(*args, **kwargs)  # type: ignore
        finally:
            self._reset_http_client()

    def _get_new_client_from_factory(self):
        return _RetrySameHTTPClient(super()._get_new_client_from_factory(), self)


class _RetrySameHTTPClient(ABCHTTPClient):
    """Companion class of NetworkContextRetrySameHTTPClient"""

    def __init__(self, http_client: ABCHTTPClient, network_content: NetworkContextRetrySameHTTPClient):
        self.http_client = http_client
        self.network_context = network_content

    def send(self, stream: bool, method: str, url: str, **kwargs) -> httpx.Response:
        retries = self.network_context._retries  # pylint: disable=protected-access
        # if retries == 1, this method can send two HTTP requets,
        # so the exit condition is self._retries must be equal or above zero
        # to allow two iteration
        while retries >= 0 and self.network_context.get_remaining_time() > 0:
            try:
                return self.http_client.send(stream, method, url, **kwargs)
            except SoftRetryHTTPException as e:
                if retries <= 0:
                    return e.response
            except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as e:
                if retries <= 0:
                    raise e
            retries -= 1
        if self.network_context.get_remaining_time() <= 0:
            raise httpx.TimeoutException("Timeout")
        raise httpx.HTTPError("Internal error: this should not happen")

    def close(self):
        return self.http_client.close()

    @property
    def is_closed(self) -> bool:
        return self.http_client.is_closed


class NetworkContextRetryDifferentHTTPClient(NetworkContext):
    """When a HTTP request fails, this NetworkContext tries again
    the same HTTP request with a different HTTP client

    The implementation wraps the provided ABCHTTPClient with _RetryDifferentHTTPClient."""

    def call(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        self._set_http_client()
        try:
            return func(*args, **kwargs)  # type: ignore
        finally:
            self._reset_http_client()

    def _get_new_client_from_factory(self):
        return _RetryDifferentHTTPClient(self)


class _RetryDifferentHTTPClient(ABCHTTPClient):
    """Companion class of NetworkContextRetryDifferentHTTPClient"""

    def __init__(self, network_context: NetworkContextRetryDifferentHTTPClient) -> None:
        self.network_context = network_context

    def send(self, stream: bool, method: str, url: str, **kwargs) -> httpx.Response:
        retries = self.network_context._retries  # pylint: disable=protected-access
        # if retries == 1, this method can send two HTTP requets,
        # so the exit condition is self._retries must be equal or above zero
        # to allow two iteration
        while retries >= 0 and self.network_context.get_remaining_time() > 0:
            http_client = self.network_context._http_client_factory()  # pylint: disable=protected-access
            try:
                return http_client.send(stream, method, url, **kwargs)
            except SoftRetryHTTPException as e:
                if retries <= 0:
                    return e.response
            except (ssl.SSLError, httpx.RequestError, httpx.HTTPStatusError) as e:
                if retries <= 0:
                    raise e
            retries -= 1
        if self.network_context.get_remaining_time() <= 0:
            raise httpx.TimeoutException("Timeout")
        raise httpx.HTTPError("Internal error: this should not happen")

    def close(self):
        raise NotImplementedError()

    @property
    def is_closed(self) -> bool:
        raise NotImplementedError()
