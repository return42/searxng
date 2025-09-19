# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=global-statement, too-many-arguments
# pylint: disable=missing-module-docstring, missing-class-docstring
"""This module implements the *network*, which essentially consists of instances
of the :py:obj:`Network` class, which are managed in
:py:obj:`searx.network.network.NETWORKS`.

The composition of the networks results from the configuration, in the
``settings.yml``.  The network configuration is hierarchical, there are global
settings in the :ref:`settings outgoing` section.  Unless configured otherwise,
each engine then has its own network, the settings of which result from the
global settings and the individual settings for the engine, see :ref:`engine
network`.
"""

__all__ = ["get_network"]

import typing as t
from collections.abc import Generator

import asyncio
import atexit
import ipaddress
import itertools
import warnings

import httpx
import httpx._types

from searx import logger, sxng_debug, get_setting
from searx.extended_types import SXNG_Response
from .client import new_client, get_loop, AsyncHTTPTransportNoHttp
from .raise_for_httperror import raise_for_httperror

if t.TYPE_CHECKING:
    import ssl

logger = logger.getChild("network")

UNSET = object()

DEFAULT_NAME: str = "__DEFAULT__"
"""Name of the default *network* in the global network container."""

NETWORKS: dict[str, "Network"] = {}
"""A global container in which the *networks* are assigned to names."""

PROXY_PATTERN_MAPPING = {
    "http": "http://",
    "https": "https://",
    "socks4": "socks4://",
    "socks5": "socks5://",
    "socks5h": "socks5h://",
    "http:": "http://",
    "https:": "https://",
    "socks4:": "socks4://",
    "socks5:": "socks5://",
    "socks5h:": "socks5h://",
}
"""Requests compatibility when reading proxy settings from ``settings.yml``."""

ADDRESS_MAPPING = {"ipv4": "0.0.0.0", "ipv6": "::"}


def get_network(name: str | None = None) -> "Network":
    return NETWORKS.get(name or DEFAULT_NAME)  # pyright: ignore[reportReturnType]


def verify_tor_proxy_works():
    # verify that Tor proxy works

    async def check():
        exception_count = 0
        for network in NETWORKS.values():
            client_args = network.get_kwargs({})[0]
            if network.using_tor_proxy:
                try:
                    await network.get_client(client_args)
                except Exception:  # pylint: disable=broad-except
                    network._logger.exception("Error")  # pylint: disable=protected-access
                    exception_count += 1
        return exception_count

    future = asyncio.run_coroutine_threadsafe(check(), get_loop())
    exception_count = future.result()
    if exception_count > 0:
        raise RuntimeError("Invalid network configuration")


class ClientArgs(t.TypedDict):
    verify: bool
    max_redirects: int
    # We set the cookies
    cookies: httpx._types.CookieTypes | None


@t.final
class Network:
    """A class to represents a *network*. The options of a *network* are mostly
    described in the :ref:`settings outgoing`.

    One of the essential tasks of a *network* is managing the HTTP clients. A
    network can be assigned to an engine or to a group of engines and this makes
    it possible for all outgoing HTTP requests in this group (in this *network*)
    to reuse existing HTTP clients.

    .. _Pool limit configuration: https://www.python-httpx.org/advanced/resource-limits/

    """

    _TOR_CHECK_RESULT = {}
    _SEND_ARG_NAMES: list[str] = ["stream", "auth"]
    _REQUEST_ARG_NAMES: list[str] = [
        "method",
        "url",
        "content",
        "data",
        "files",
        "json",
        "params",
        "headers",
        # "cookies",   # see client_args["cookies"]
        "timeout",
        "extensions",
    ]

    # FIXME: default parameters for AsyncHTTPTransport
    # FIXME: see https://github.com/encode/httpx/blob/e05a5372eb6172287458b37447c30f650047e1b8/httpx/_transports/default.py#L108-L121  # pylint: disable=line-too-long
    DEFAULT_SETTINGS = {
        # values from section 'outgoing:'
        "enable_http2": "outgoing.enable_http2",
        "keepalive_expiry": "outgoing.keepalive_expiry",
        "local_addresses": "outgoing.source_ips",
        "max_connections": "outgoing.pool_connections",
        "max_keepalive_connections": "outgoing.pool_maxsize",
        "max_redirects": "outgoing.max_redirects",
        "proxies": "outgoing.proxies",
        "retries": "outgoing.retries",
        "using_tor_proxy": "outgoing.using_tor_proxy",
        "verify": "outgoing.verify",
        # other network settings
        "enable_http": False,
        "retry_on_http_error": False,
    }

    @classmethod
    def get_defaults(cls) -> dict[str, t.Any]:
        """Builds up a dictionary with the default network settings, based on
        the global settings (aka settings.yml) / see :py:obj:`DEFAULT_SETTINGS`.
        """
        kwargs: dict[str, t.Any] = {}
        for name, val in cls.DEFAULT_SETTINGS.items():
            if isinstance(val, str):
                val = get_setting(val, UNSET)
            if val is not UNSET:
                kwargs[name] = val
        return kwargs

    def __init__(
        self,
        enable_http: bool = True,
        verify: "ssl.SSLContext | str | bool" = True,
        enable_http2: bool = False,
        max_connections: int | None = None,
        max_keepalive_connections: int | None = None,
        keepalive_expiry: float | None = None,
        proxies: str | dict[str, str] | None = None,
        using_tor_proxy: bool = False,
        local_addresses: str | list[str] | None = None,
        retries: int = 0,
        retry_on_http_error: bool | list[int] | int = False,
        max_redirects: int = 30,
        name: str | None = None,
    ):

        self.name = name

        self.enable_http = enable_http
        """Enable HTTP for this engine, by default only HTTPS is enabled
        (cfg: ````)."""

        self.enable_http2 = enable_http2
        """Enable by default.  Set to ``false`` to disable HTTP/2.

        - `httpx.Client.http2 <https://www.python-httpx.org/api/#client>`__
        """

        self.keepalive_expiry = keepalive_expiry
        """`Pool limit configuration`_"""

        self.max_connections = max_connections
        """`Pool limit configuration`_"""

        self.max_keepalive_connections = max_keepalive_connections
        """`Pool limit configuration`_"""

        self.local_addresses = local_addresses
        """See :ref:`source_ips <outgoing.source_ips>`"""

        self.max_redirects = max_redirects
        """Maximum redirects before outgoing request is error
        (``outgoing.max_redirects``):

        - `httpx.Client.max_redirects <https://www.python-httpx.org/api/#client>`_
        """

        self.proxies = proxies
        """See :ref:`proxies <outgoing.proxies>`."""

        self.retries = retries
        """Number of request retries before the outgoing HTTP request is
        considered failed (``outgoing.retries``).  On each retry, a different
        proxy and source ip (:py:obj:`Network.local_addresses`) is used.
        """

        self.retry_on_http_error = retry_on_http_error
        """Retry request on some HTTP status code.

        Example:

        - ``True`` : on HTTP status code between 400 and 599.
        - ``403`` : on HTTP status code 403.
        - ``[403, 429]``: on HTTP status code 403 and 429.
        """

        self.using_tor_proxy = using_tor_proxy
        """Using tor proxy (``True``) or not (``False``) for all engines."""

        self.verify = verify
        """Either ``True`` to use an SSL context with the default CA bundle,
        False to disable verification, or an instance of
        :py:obj:`ssl.SSLContext` to use a custom context.

        - `httpx.Client.verify <https://www.python-httpx.org/api/#client>`__
        - `httpx ssl configuration`_

        .. _httpx ssl configuration:
            https://www.python-httpx.org/compatibility/#ssl-configuration
        """

        self.local_addresses_cycle = self._local_address_cycle_generator()
        self.proxies_cycle = self._proxies_cycle_generator()
        self._clients = {}
        self.log = logger.getChild(name) if name else logger

        self.check_parameters()

    def check_parameters(self):
        if not self.local_addresses and not self.proxies:
            self.log.warning(
                f"network {self.name} is missing a config for local_addresses or proxies",
            )

        for address in self.iter_local_addresses():
            if '/' in address:
                ipaddress.ip_network(address, False)
            else:
                ipaddress.ip_address(address)

        if self.proxies is not None and not isinstance(self.proxies, (str, dict)):
            raise ValueError("proxies type has to be str, dict or None")

    def iter_local_addresses(self) -> Generator[str]:
        local_addresses = self.local_addresses
        if not local_addresses:
            return
        if isinstance(local_addresses, str):
            local_addresses = [local_addresses]
        yield from local_addresses

    def iter_proxies(self) -> Generator[tuple[str, list[str]]]:
        if not self.proxies:
            return
        pattern: str
        proxy_urls: list[str] | str

        # https://www.python-httpx.org/compatibility/#proxy-keys
        if isinstance(self.proxies, str):
            proxy_urls = [self.proxies]
            pattern = "all://"
            yield pattern, proxy_urls

        elif isinstance(self.proxies, dict):
            for pattern, proxy_urls in self.proxies.items():
                pattern = PROXY_PATTERN_MAPPING.get(pattern, pattern)
                if isinstance(proxy_urls, str):
                    proxy_urls = [proxy_urls]
                yield pattern, proxy_urls

    def _local_address_cycle_generator(self) -> Generator[str | None]:
        while True:  # cycle runs for ever
            count = 0
            for address in self.iter_local_addresses():
                if '/' in address:
                    for a in ipaddress.ip_network(address, False).hosts():
                        yield str(a)
                        count += 1
                else:
                    a = ipaddress.ip_address(address)
                    yield str(a)
                    count += 1
            if count == 0:
                yield None

    def _proxies_cycle_generator(self) -> Generator[tuple[str, str | None] | None]:
        proxy_settings: dict[str, itertools.cycle[str]] = {}
        for pattern, proxy_urls in self.iter_proxies():
            proxy_url_cycle = itertools.cycle(proxy_urls)
            proxy_settings[pattern] = proxy_url_cycle

        while True:
            count = 0
            for pattern, proxy_url_cycle in proxy_settings.items():
                yield pattern, next(proxy_url_cycle)
                count += 1
            if count == 0:
                yield None

    async def log_response(self, response: httpx.Response):
        request = response.request
        status = f"{response.status_code} {response.reason_phrase}"
        response_line = f"{response.http_version} {status}"
        content_type = response.headers.get("Content-Type", "")
        content_type = f" ({content_type})" if content_type else ""
        self.log.debug(f"HTTP Request: {request.method} {request.url} '{response_line}'{content_type}")

    XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXx

    @staticmethod
    async def check_tor_proxy(client: httpx.AsyncClient, proxies: tuple[str, str | None] | None) -> bool:
        if proxies in Network._TOR_CHECK_RESULT:
            return Network._TOR_CHECK_RESULT[proxies]

        result = True

        # ignore client._transport because it is not used with all://
        for transport in client._mounts.values():  # pylint: disable=protected-access
            if isinstance(transport, AsyncHTTPTransportNoHttp):
                continue
            if getattr(transport, "_pool") and getattr(
                # pylint: disable=protected-access
                transport._pool,  # type: ignore
                "_rdns",
                False,
            ):
                continue
            return False

        response = await client.get("https://check.torproject.org/api/ip", timeout=60)
        if not response.json()["IsTor"]:
            result = False
        Network._TOR_CHECK_RESULT[proxies] = result
        return result

    async def get_client(self, kwargs: ClientArgs) -> httpx.AsyncClient:
        verify = kwargs.get("verify", self.verify)
        max_redirects = kwargs.get("max_redirects", self.max_redirects)
        local_address = next(self.local_addresses_cycle)
        proxies = next(self.proxies_cycle)  # is a tuple so it can be part of the key
        key = (verify, max_redirects, local_address, proxies)
        hook_log_response = self.log_response if sxng_debug else None
        if key not in self._clients or self._clients[key].is_closed:
            client = new_client(
                self.enable_http,
                verify,
                self.enable_http2,
                self.max_connections,
                self.max_keepalive_connections,
                self.keepalive_expiry,
                dict(proxies),  # create a copy of the proxy settings
                local_address,
                0,
                max_redirects,
                hook_log_response,
            )
            if self.using_tor_proxy and not await self.check_tor_proxy(client, proxies):
                await client.aclose()
                raise httpx.ProxyError('Network configuration problem: not using Tor')
            self._clients[key] = client
        return self._clients[key]

    async def aclose(self):
        async def close_client(client):
            try:
                await client.aclose()
            except httpx.HTTPError:
                pass

        await asyncio.gather(*[close_client(client) for client in self._clients.values()], return_exceptions=False)

    @classmethod
    async def aclose_all(cls):
        await asyncio.gather(*[network.aclose() for network in NETWORKS.values()], return_exceptions=False)

    def patch_response(self, response: httpx.Response, kwargs: dict[str, t.Any]) -> SXNG_Response:

        if isinstance(response, httpx.Response):
            response = t.cast(SXNG_Response, response)
            # requests compatibility (response is not streamed)
            # see also https://www.python-httpx.org/compatibility/#checking-for-4xx5xx-responses
            response.ok = not response.is_error

            if kwargs.get("raise_for_httperror"):
                try:
                    raise_for_httperror(response)
                except:
                    self.log.warning(f"HTTP Request failed: {response.request.method} {response.request.url}")
                    raise
        return response

    def do_retry_on_http_error(self, response: httpx.Response) -> bool:
        # pylint: disable=too-many-boolean-expressions
        if isinstance(self.retry_on_http_error, bool):
            if self.retry_on_http_error and 400 <= response.status_code <= 599:
                return True
        elif isinstance(self.retry_on_http_error, list):
            if response.status_code in self.retry_on_http_error:
                return True
        elif isinstance(self.retry_on_http_error, int):
            if response.status_code == self.retry_on_http_error:
                return True
        return True

    def get_kwargs(self, kwargs: dict[str, t.Any]) -> tuple[ClientArgs, dict[str, t.Any], dict[str, t.Any]]:
        """Generates a tuple with three dictionaries from the ``**kwargs``.

        - The first dictionary contains the arguments needed to build a client
          (:py:obj:`Network.get_client)`.

        - The second dictionary contains the arguments needed to build a request
          (:py:obj:`httpx.BaseClient.build_request`).

        - The third dictionary contains the arguments needed to send a request
          (:py:obj:`httpx.BaseClient.send`).

        """

        def _set(_d: dict[str, t.Any], names: list[str]):
            for arg_name in names:
                val = kwargs.get(arg_name, UNSET)
                if val is not UNSET:
                    _d[arg_name] = val

        client_args: ClientArgs = {
            "verify": kwargs.get("verify", self.verify),
            "max_redirects": kwargs.get("max_redirects", self.max_redirects),
            # hint: we set the c
            "cookies": kwargs.get("cookies", None),
        }

        # see https://github.com/encode/httpx/pull/1808
        req_args: dict[str, t.Any] = {}
        req_args["follow_redirects"] = kwargs.get("allow_redirects", False)
        _set(req_args, self._REQUEST_ARG_NAMES)

        send_args: dict[str, t.Any] = {}
        send_args["follow_redirects"] = kwargs.get("allow_redirects", False)
        _set(send_args, self._SEND_ARG_NAMES)

        return client_args, req_args, send_args

    async def call_client(self, **kwargs: t.Any) -> SXNG_Response:
        client_args, req_args, send_args = self.get_kwargs(**kwargs)
        c = self.retries + 1
        was_disconnected = False  # IDK if this is any longer needed

        response = None
        while c >= 0:
            c = -1
            client: httpx.AsyncClient = await self.get_client(client_args)
            request = client.build_request(**req_args)
            try:
                response = await client.send(request, **send_args)
                if self.do_retry_on_http_error(response):
                    continue
                return self.patch_response(response, kwargs=kwargs)

            except httpx.RemoteProtocolError as exc:
                if not was_disconnected:
                    # IDK if this is any longer true: the server has closed the
                    # connection.
                    was_disconnected = True
                    # Try again without decreasing the retries variable & with a
                    # new HTTP client
                    await client.aclose()
                    self.log.warning("httpx.RemoteProtocolError: the server has disconnected, retrying")
                    continue
                if c <= 0:
                    raise exc

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if c <= 0:
                    raise exc

        raise ValueError(
            f"No response object for {kwargs.get('method')}:" f"  {kwargs.get('url')} in {self.retries} retries"
        )

    async def request(self, **kwargs: t.Any) -> SXNG_Response:
        return await self.call_client(**kwargs)

    # XXXXXXXXXXXXXXXXXXXXXXXx

    # async def stream(self, method: str, url: str, **kwargs):
    #     return await self.call_client(True, method, url, **kwargs)

    # async def stream(self, method: str, url: str, **kwargs: t.Any):
    #     client_args, req_args = self.get_kwargs(**kwargs)
    #     c = self.retries + 1

    #     response = None
    #     while c >= 0:
    #         c = -1
    #         client = await self.get_client(client_args)
    #         try:
    #             request = client.build_request(**req_args)
    #             response = await self.send(
    #                 request=request,
    #                 auth=auth,
    #                 follow_redirects=follow_redirects,
    #                 stream=True,
    #             )

    #             response = client.stream(method, url, **req_args)  # pyright: ignore[reportAny]

    #         except (
    #             httpx.RemoteProtocolError,
    #             httpx.RequestError,
    #             httpx.HTTPStatusError,
    #         ) as exc:
    #             if c <= 0:
    #                 raise exc

    #     client_args, req_args = self.get_kwargs(**kwargs)
    #     return response

    # # async def call_client(self, stream: bool, method: str, url: str, **kwargs: t.Any) -> SXNG_Response:
    # #     retries = self.retries
    # #     was_disconnected = False
    # #     do_raise_for_httperror = Network.extract_do_raise_for_httperror(kwargs)
    # #     kwargs_clients = Network.extract_kwargs_clients(kwargs)
    # #     while retries >= 0:
    # #         client = await self.get_client(**kwargs_clients)
    # #         cookies = kwargs.pop("cookies", None)
    # #         client.cookies = httpx.Cookies(cookies)
    # #         try:
    # #             if stream:
    # #                 response = client.stream(method, url, **kwargs)
    # #             else:
    # #                 response = await client.request(method, url, **kwargs)
    # #             if self.is_valid_response(response) or retries <= 0:
    # #                 return self.patch_response(response, do_raise_for_httperror)
    # #         except httpx.RemoteProtocolError as e:
    # #             if not was_disconnected:
    # #                 # the server has closed the connection:
    # #                 # try again without decreasing the retries variable & with a new HTTP client
    # #                 was_disconnected = True
    # #                 await client.aclose()
    # #                 self.log.warning('httpx.RemoteProtocolError: the server has disconnected, retrying')
    # #                 continue
    # #             if retries <= 0:
    # #                 raise e
    # #         except (httpx.RequestError, httpx.HTTPStatusError) as e:
    # #             if retries <= 0:
    # #                 raise e
    # #         retries -= 1


def initialize(
    settings_engines: list[dict[str, t.Any]] = None,  # pyright: ignore[reportArgumentType]
    settings_outgoing: dict[str, t.Any] = None,  # pyright: ignore[reportArgumentType]
) -> None:
    # pylint: disable=import-outside-toplevel
    from searx.engines import engines
    from searx import settings

    # pylint: enable=import-outside-toplevel
    settings_engines = settings_engines or settings["engines"]
    settings_outgoing = settings_outgoing or settings["outgoing"]
    network_defaults = Network.get_defaults()

    def new_network(params: dict[str, t.Any], name: str):
        nonlocal network_defaults
        kwargs: dict[str, t.Any] = {"name": name}
        kwargs.update(network_defaults)
        kwargs.update(params)
        return Network(**kwargs)

    def iter_networks():
        nonlocal network_defaults
        nonlocal settings_engines

        for engine_spec in settings_engines:
            engine_name = str(engine_spec["name"])
            engine = engines.get(engine_name)
            if engine is None:
                continue
            network_cfg: dict[str, t.Any] | str | None = getattr(engine, "network", None)
            yield engine_name, engine, network_cfg

    if NETWORKS:
        done()

    NETWORKS.clear()
    NETWORKS[DEFAULT_NAME] = new_network({}, name=DEFAULT_NAME)
    NETWORKS["ipv4"] = new_network({"local_addresses": "0.0.0.0"}, name="ipv4")
    NETWORKS["ipv6"] = new_network({"local_addresses": "::"}, name="ipv6")

    # the /image_proxy endpoint has a dedicated network, named:
    name = "image_proxy"
    if name not in NETWORKS:
        # Like default network, but HTTP/2 is disabled.  It decreases the CPU
        # load average, and the total time is more or less the same.
        NETWORKS[name] = new_network({"enable_http2": False}, name=name)

    # define networks from outgoing.networks
    for name, network in settings_outgoing["networks"].items():
        NETWORKS[name] = new_network(network, name=name)

    # define networks from engines.[i].network
    for engine_name, engine, network_cfg in iter_networks():
        network_cfg: dict[str, t.Any] | str | None

        if isinstance(network_cfg, str):
            # the network is referenced by its name
            NETWORKS[engine_name] = NETWORKS[network_cfg]
            continue

        if isinstance(network_cfg, dict):
            NETWORKS[engine_name] = new_network(network_cfg, name=engine_name)
            continue

        if network_cfg is None:
            # deprecated: network options are set in the engine options
            network_cfg = {}
            for attribute_name in network_defaults.keys():
                if hasattr(engine, attribute_name):
                    network_cfg[attribute_name] = getattr(engine, attribute_name)
            if network_cfg:
                warnings.warn(
                    f"engine {engine_name} setting network config"
                    f" [{'|'.join(network_cfg.keys())}] is deprecated,"
                    f" use engine.network.*",
                    DeprecationWarning,
                )
                NETWORKS[engine_name] = new_network(network_cfg, name=engine_name)
        else:
            raise ValueError(
                f"engine {engine_name} network config: unknown type {type(network_cfg)}"
            )  # pyright: ignore[reportUnreachable]


@atexit.register
def done():
    """Close all HTTP client

    Avoid a warning at exit
    See https://github.com/encode/httpx/pull/2026

    Note: since Network.aclose has to be async, it is not possible to call this method on Network.__del__
    So Network.aclose is called here using atexit.register
    """
    try:
        loop = get_loop()
        if loop:
            future = asyncio.run_coroutine_threadsafe(Network.aclose_all(), loop)
            # wait 3 seconds to close the HTTP clients
            future.result(3)
    finally:
        NETWORKS.clear()


NETWORKS[DEFAULT_NAME] = Network()
