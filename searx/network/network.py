# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
# pylint: disable=missing-class-docstring
# pyright: basic
"""This module implements the network, which essentially consists of instances
of the :py:obj:`Network` class, which are managed in a :py:obj:`NetworkManager`.

The composition of the networks results from the settings, in the
``settings.yml``.  The network settings are hierarchical, there are global
settings in the :ref:`settings outgoing` section.  Unless configured otherwise,
each engine then has its own network, the settings of which result from the
global settings and the individual settings for the engine.

The individual characteristics of :py:obj:`Network` are determined by the
individual :py:obj:`NetworkSettings` and they are managed in the
:py:obj:`NetworkManager`.

"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from enum import Enum
from itertools import cycle
from typing import Any, Mapping

import httpx

from searx import logger, searx_debug
from searx.network.client import HTTPClient, TorHTTPClient
from searx.network.context import (
    NetworkContext,
    NetworkContextRetryDifferentHTTPClient,
    NetworkContextRetryFunction,
    NetworkContextRetrySameHTTPClient,
)

logger = logger.getChild('network')


class RetryStrategy(Enum):
    """Enumeration of available *retry-strategies*.  The retry strategy of a
    HTTP request is defined by the :py:obj:`NetworkContext`."""

    ENGINE = NetworkContextRetryFunction
    SAME_HTTP_CLIENT = NetworkContextRetrySameHTTPClient
    DIFFERENT_HTTP_CLIENT = NetworkContextRetryDifferentHTTPClient


TYPE_IP_ANY = (
    ipaddress.IPv4Address | ipaddress.IPv6Address | ipaddress.IPv4Network | ipaddress.IPv6Network
)  # pylint: disable=invalid-name

TYPE_RETRY_ON_ERROR = list[int] | int | bool  # pylint: disable=invalid-name


@dataclass(order=True, frozen=True)
class NetworkSettings:
    """The instances of this class encapsulate the network settings that
    parameterize a :py:obj:`Network` instance.  The *network settings* are
    defined in ``settings.yml`` / the global defaults are defined in the
    :ref:`outgoing <settings outgoing>` settings.

    If the network configuration is read from the ``settings.yml``, the
    instances of this class are created via a helper class
    :py:obj:`NetwortSettingsDecoder`.

    .. todo::

       - Is a separation of dataclass and methods really necessary?

         TLDR: It should be considered whether the construct of an auxiliary
         class for object creation can be dispensed with. The
         :py:obj:`NetwortSettingsDecoder` only has class methods and static
         methods, these can actually also be all methods of
         :py:obj:`NetworkSettings`.

       - check if we need order=True

    """

    # Individual HTTP requests can override these parameters.
    verify: bool = True
    """see :ref:`outgoing.verify`"""

    max_redirects: int = 30
    """see :ref:`outgoing.max_redirects`"""

    # These parameters can not be overridden.

    enable_http: bool = False  # disable http:// URL (unencrypted) by default = make sure to use HTTPS
    """HTTPS only"""

    enable_http2: bool = True
    """see :ref:`outgoing.enable_http2`"""

    # limits
    max_connections: int | None = 10
    """see :ref:`outgoing.pool_connections`"""

    max_keepalive_connections: int | None = 100
    """see :ref:`outgoing.pool_maxsize`"""

    keepalive_expiry: float | None = 5.0
    """see :ref:`outgoing.keepalive_expiry`"""

    local_addresses: list[TYPE_IP_ANY] = field(default_factory=list)
    """see :ref:`outgoing.source_ips`"""

    proxies: dict[str, list[str]] = field(default_factory=dict)
    """see :ref:`outgoing.proxies`"""

    using_tor_proxy: bool = False
    """see :ref:`outgoing.using_tor_proxy`"""

    retries: int = 0
    """see :ref:`outgoing.retries`"""

    retry_strategy: RetryStrategy = RetryStrategy.DIFFERENT_HTTP_CLIENT
    """:py:obj:`RetryStrategy` (:py:obj:`NetworkContext`) of the
    :py:obj:`Network`.  The default strategy is :py:obj:`DIFFERENT_HTTP_CLIENT
    <NetworkContextRetryDifferentHTTPClient>`."""

    retry_on_http_error: TYPE_RETRY_ON_ERROR | None = None
    """see :ref:`engine.retry_on_http_error`"""

    logger_name: str | None = None
    """Name of the network's logger.  The :py:obj:`NetworkManager` sets it to
    the name of the network."""


class Network:
    """Instances of class :py:obj:`Network` are build from
    :py:obj:`NetworkSettings` and consist mainly of a :py:obj:`NetworkContext`
    (:py:obj:`RetryStrategy`) and a :py:obj:`HTTP client
    <.client.ABCHTTPClient>` instance.

    A Network might have multiple IP addresses and proxies; in this case, each
    call to :py:obj:`self.get_context` or :py:obj:`self.get_http_client`
    provides a different configuration.

    :ivar _settings: A instance of :py:obj:`NetworkSettings`

    :ivar _local_addresses_cycle: A generator that rotates infinitely over the
      local IP addresses aka :ref:`source_ips <outgoing.source_ips>`
      (:py:obj:`Network._get_local_addresses_cycle`)

    :ivar _proxies_cycle: A generator that rotates infinitely over the
      :ref:`proxies <outgoing.proxies>` (:py:obj:`Network._get_proxy_cycles`)

    :ivar _clients: A mapping in which the :py:obj:`HTTPClient` are managed on
      the basis of selected client properties
      (:py:obj:`Network._get_http_client`).

    :ivar _logger: A logger that is passed to the :py:obj:`HTTPClient`.  The
      name of the logger comes from :py:obj:`NetworkSettings.logger_name`

    """

    __slots__ = (
        '_settings',
        '_local_addresses_cycle',
        '_proxies_cycle',
        '_clients',
        '_logger',
    )

    def __init__(self, settings: NetworkSettings):
        """Creates a Network from a NetworkSettings"""
        self._settings = settings
        self._local_addresses_cycle = self._get_local_addresses_cycle()
        self._proxies_cycle = self._get_proxy_cycles()
        self._clients: dict[tuple, HTTPClient] = {}
        self._logger = logger.getChild(settings.logger_name) if settings.logger_name else logger

    @staticmethod
    def from_dict(**kwargs):
        """Creates a Network from a keys/values

        .. todo::

           We should consider dropping this factory method as it bypasses the
           typing we did in :py:obj:`NetworkSettings`.  The typing is only
           re-established by the decoder .. when a decoder is needed, then the
           caller should use the decoder directly to generate a
           :py:obj:`NetworkSettings` instance. / Too many indirections impair
           the readability of the code.

        """
        return Network(NetwortSettingsDecoder.from_dict(kwargs))

    def close(self):
        """Closes all :py:obj:`HTTPClient` instances that are managed in this
        network."""

        for client in self._clients.values():
            client.close()

    def check_configuration(self) -> bool:
        """Check if the network configuration is valid.  Typical use case is to
        check if the proxy is really a Tor proxy."""

        try:
            self._get_http_client()
            return True
        except Exception:  # pylint: disable=broad-except
            self._logger.exception('Error')
            return False

    def get_context(self, timeout: float | None = None, start_time: float | None = None) -> NetworkContext:
        """Creates a new :py:obj:`NetworkContext` object from the configured
        :py:obj:`NetworkSettings.retry_strategy`."""

        context_cls = self._settings.retry_strategy.value
        return context_cls(self._settings.retries, self._get_http_client, start_time, timeout)

    def _get_http_client(self) -> HTTPClient:
        """Returns a HTTP client.

        The network manages instances of :py:obj:`HTTPClient` by local IP
        addresses (aka :ref:`source_ips <outgoing.source_ips>`) and
        :ref:`proxies <outgoing.proxies>`.

        For each pair of a individual combination of the *local IP address* and
        *proxy setup* a client is instanciated and added to the client mapping
        in :py:obj:`Network._clients`.

        - The variations of the *local IP address* result from the
          :py:obj:`Network._local_addresses_cycle` generator.

        - The variations of `proxies (httpx)`_ result from the
          :py:obj:`Network._proxies_cycle` generator.

        - Clients are reused and cached by a key that combines:

             key = ( <local IP address>, `proxies (httpx)`_)

        The HTTP client instances returned by this method therefore rotate over
        all variations resulting from the rotating generators.  For each
        individual combination, a client is instantiated only once and reused
        from then on when the rotation has reached the same variation again.

        For example, if two proxies are defined (and no local IP):

          The first call to this function returns an HTTP client using the first
          proxy.  A second call returns an HTTP client using the second proxy.
          A third call returns the same HTTP client from the first call, using
          the first proxy.

        .. _proxies (httpx): https://www.python-httpx.org/advanced/#http-proxying

        """
        local_address = next(self._local_addresses_cycle)
        proxies = next(self._proxies_cycle)  # is a tuple so it can be part of the key
        key = (local_address, proxies)

        if key not in self._clients or self._clients[key].is_closed:
            http_client_cls = TorHTTPClient if self._settings.using_tor_proxy else HTTPClient
            hook_log_response = self._log_response if searx_debug else None
            log_trace = self._log_trace if searx_debug else None
            self._clients[key] = http_client_cls(
                verify=self._settings.verify,
                enable_http=self._settings.enable_http,
                enable_http2=self._settings.enable_http2,
                max_connections=self._settings.max_connections,
                max_keepalive_connections=self._settings.max_keepalive_connections,
                keepalive_expiry=self._settings.keepalive_expiry,
                proxies=dict(proxies),
                local_address=local_address,
                retry_on_http_error=self._settings.retry_on_http_error,
                hook_log_response=hook_log_response,
                log_trace=log_trace,
                logger=self._logger,
            )
        return self._clients[key]

    def _get_local_addresses_cycle(self):
        """Generator that rotates infinitely over the local IP addresses from
        :py:obj:`NetworkSettings.local_addresses` (:ref:`source_ips
        <outgoing.source_ips>`)."""

        while True:
            at_least_one = False
            for address in self._settings.local_addresses:
                if isinstance(address, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
                    for a in address.hosts():
                        yield str(a)
                        at_least_one = True
                else:
                    yield str(address)
                    at_least_one = True
            if not at_least_one:
                # IPv4Network.hosts() and IPv6Network.hosts() might never return an IP address.
                # at_least_one makes sure the generator does not turn into infinite loop without yield
                yield None

    def _get_proxy_cycles(self):
        """A generator that rotates infinitely over the :ref:`proxies
        <outgoing.proxies>`.  When no proxies are configured, this generator
        returns an empty tuple at each iteration.

        The following configuration, in which two proxies are configured, is
        shown as an example:

        .. code:: yaml

           proxies:
               - all://:
                    - socks5h://localhost:4000
                    - socks5h://localhost:5000
                    - socks5h://localhost:6000

        Three HTTP clients can be built from this configuration, one communicates
        via the socket on port 4000, the others via the sockets on port 5000 and
        6000.  This generator circulates over the three possible values:

        .. code:: python

           # first
           ( ('all://', 'socks5h://localhost:4000'), )

           # second
           ( ('all://', 'socks5h://localhost:5000'), )

           # third
           ( ('all://', 'socks5h://localhost:6000'), )

        SearXNG's network allows to have more complex setups.  For instance we
        can alternate bing requests over two proxies (5000 & 6000) and all other
        requests go over a third proxy (4000):

        .. code:: yaml

           proxies:
               - all://:
                    - socks5h://localhost:4000
               - https://bing.com:
                    - socks5h://localhost:5000
                    - socks5h://localhost:6000

        In this example, this generator alternately returns these two responses:

        .. code:: python

           # first
           ( ('all://', 'socks5h://localhost:4000'),
             ('https://bing.com', 'socks5h://localhost:4000'),
           )

           # second
           ( ('all://', 'socks5h://localhost:4000'),
             ('https://bing.com', 'socks5h://localhost:5000'),
           )

        Semantically, these are dict-types, but this generator use tuple-types
        because the :py:obj:`Network._get_http_client` method can use them
        directly as keys for caching the HTTP clients.  A dict-type can be build
        by ``dict(next(self._proxies_cycle))``.

        Finally, an example where only one proxy is configured and there is no
        mapping of a url-protocol:

        .. code:: yaml

           proxies: socks5h://localhost:4000

        what is a short notation of:

        .. code:: yaml

           proxies:
               - all://:
                 - socks5h://localhost:4000

        With such a setup, the generator would return the same (one) tuple with
        every ``next`` call.

        .. code:: python

           # first one (and only)
           ( ('all://', 'socks5h://localhost:4000'), )
        """
        # for each pattern, turn each list of proxy into a cycle
        proxy_settings = {pattern: cycle(proxy_urls) for pattern, proxy_urls in (self._settings.proxies).items()}
        while True:
            # pylint: disable=stop-iteration-return
            # ^^ is it a pylint bug ?
            yield tuple((pattern, next(proxy_url_cycle)) for pattern, proxy_url_cycle in proxy_settings.items())

    def _log_response(self, response: httpx.Response):
        """Logging function that is registered in the event-hooks_ of the
        httpx-client.

        .. todo::

           A major disadvantage of this implementation (which logs the request
           in the response) is that a request is only logged if there is a
           response to it.  However, these are precisely the cases that you want
           to debug where there is no response to the request.

           It would be better if the network instance defines loggers for
           request and response in an event-map and passes the event-map
           directly to the http-client's event-hooks_.

        Logs from httpx are disabled. Log the HTTP response with the logger from the network

        .. _event-hooks: https://www.python-httpx.org/advanced/#event-hooks
        """

        request = response.request
        status = f"{response.status_code} {response.reason_phrase}"
        response_line = f"{response.http_version} {status}"
        content_type = response.headers.get("Content-Type")
        content_type = f' ({content_type})' if content_type else ''
        self._logger.debug(f'HTTP Request: {request.method} {request.url} "{response_line}"{content_type}')

    def _log_trace(self, name: str, info: Mapping[str, Any]) -> None:
        """Logs the actual source & dest IPs and the SSL cipher.  This method is
        registered in the `httpcore request-extensions`_.

        .. _httpcore request-extensions: https://www.encode.io/httpcore/extensions/#request-extensions

        .. note::

           Does not work with socks proxy / see:

           - https://www.encode.io/httpcore/extensions/
           - https://github.com/encode/httpx/blob/e874351f04471029b2c5dcb2d0b50baccc7b9bc0/httpx/_main.py#L207

        """
        if name == "connection.connect_tcp.complete":
            stream = info["return_value"]
            server_addr = stream.get_extra_info("server_addr")
            client_addr = stream.get_extra_info("client_addr")
            self._logger.debug(f"* Connected from {client_addr[0]!r} to {server_addr[0]!r} on port {server_addr[1]}")
        elif name == "connection.start_tls.complete":  # pragma: no cover
            stream = info["return_value"]
            ssl_object = stream.get_extra_info("ssl_object")
            version = ssl_object.version()
            cipher = ssl_object.cipher()
            alpn = ssl_object.selected_alpn_protocol()
            self._logger.debug(f"* SSL established using {version!r} / {cipher[0]!r}, ALPN protocol: {alpn!r}")
        elif name == "http2.send_request_headers.started":
            self._logger.debug(f"* HTTP/2 stream_id: {info['stream_id']}")

    def __repr__(self):
        return f"<{self.__class__.__name__} logger_name={self._settings.logger_name!r}>"


class NetwortSettingsDecoder:
    """Convert a description of a network in settings.yml to a NetworkSettings instance"""

    # requests compatibility when reading proxy settings from settings.yml
    PROXY_PATTERN_MAPPING = {
        'http': 'http://',
        'https': 'https://',
        'socks4': 'socks4://',
        'socks5': 'socks5://',
        'socks5h': 'socks5h://',
        'http:': 'http://',
        'https:': 'https://',
        'socks4:': 'socks4://',
        'socks5:': 'socks5://',
        'socks5h:': 'socks5h://',
    }

    @classmethod
    def from_dict(cls, network_settings: dict[str, Any]) -> NetworkSettings:
        # Decode the parameters that require it; the other parameters are left as they are
        decoders = {
            "proxies": cls._decode_proxies,
            "local_addresses": cls._decode_local_addresses,
            "retry_strategy": cls._decode_retry_strategy,
        }
        for key, decode_func in decoders.items():
            if key not in network_settings:
                continue
            if network_settings[key] is None:
                # None is seen as not set: rely on the default values from NetworkSettings
                del network_settings[key]
            else:
                network_settings[key] = decode_func(network_settings[key])
        # Relies on the default values of NetworkSettings for unset parameters
        return NetworkSettings(**network_settings)

    @classmethod
    def _decode_proxies(cls, proxies) -> dict[str, list[str]]:
        if isinstance(proxies, str):
            # for example:
            # proxies: socks5://localhost:8000
            proxies = {'all://': [proxies]}
        elif isinstance(proxies, list):
            # for example:
            # proxies:
            #   - socks5h://localhost:8000
            #   - socks5h://localhost:8001
            proxies = {'all://': proxies}

        if not isinstance(proxies, dict):
            raise ValueError('proxies type has to be str, list, dict or None')

        # Here we are sure to have
        # proxies = {
        #   pattern: a_value
        # }
        # with a_value that can be either a string or a list.
        # Now, we make sure that a_value is always a list of strings.
        # Also, we keep compatibility with requests regarding the patterns:
        # see https://www.python-httpx.org/compatibility/#proxy-keys
        result = {}
        for pattern, proxy_list in proxies.items():
            pattern = cls.PROXY_PATTERN_MAPPING.get(pattern, pattern)
            if isinstance(proxy_list, str):
                proxy_list = [proxy_list]
            if not isinstance(proxy_list, list):
                raise ValueError('proxy list')
            for proxy in proxy_list:
                if not isinstance(proxy, str):
                    raise ValueError(f'{repr(proxy)} : an URL is expected')
            result[pattern] = proxy_list
        return result

    @staticmethod
    def _decode_local_addresses(ip_addresses: str | list[str]) -> list[TYPE_IP_ANY]:
        if isinstance(ip_addresses, str):
            ip_addresses = [ip_addresses]

        if not isinstance(ip_addresses, list):
            raise ValueError('IP address must be either None or a string or a list of strings')

        # check IP address syntax
        result = []
        for address in ip_addresses:
            if not isinstance(address, str):
                raise ValueError(f'An {address!r} must be an IP address written as a string')
            if '/' in address:
                result.append(ipaddress.ip_network(address, False))
            else:
                result.append(ipaddress.ip_address(address))
        return result

    @staticmethod
    def _decode_retry_strategy(retry_strategy: str) -> RetryStrategy:
        for member in RetryStrategy:
            if member.name.lower() == retry_strategy.lower():
                return member
        raise ValueError(f"{retry_strategy} is not a RetryStrategy")


class NetworkManager:
    """Contains all the Network instances.

    By default, there is one default network with the default parameters,
    so @searx.network.provide_networkcontext() works out of the box.
    """

    DEFAULT_NAME = '__DEFAULT__'

    def __init__(self):
        # Create a default network so scripts in searxng_extra don't have load settings.yml
        self.networks: dict[str, Network] = {NetworkManager.DEFAULT_NAME: Network.from_dict()}

    def get(self, name: str | None = None):
        return self.networks[name or NetworkManager.DEFAULT_NAME]

    def initialize_from_settings(self, settings_engines, settings_outgoing, check=True):

        # pylint: disable=too-many-branches
        from searx.engines import engines  # pylint: disable=import-outside-toplevel

        # Default parameters for HTTPTransport
        # see https://github.com/encode/httpx/blob/e05a5372eb6172287458b37447c30f650047e1b8/httpx/_transports/default.py#L108-L121  # pylint: disable=line-too-long
        default_network_settings = {
            'verify': settings_outgoing['verify'],
            'enable_http': settings_outgoing['enable_http'],
            'enable_http2': settings_outgoing['enable_http2'],
            'max_connections': settings_outgoing['pool_connections'],  # different because of historical reason
            'max_keepalive_connections': settings_outgoing['pool_maxsize'],  # different because of historical reason
            'keepalive_expiry': settings_outgoing['keepalive_expiry'],
            'max_redirects': settings_outgoing['max_redirects'],
            'retries': settings_outgoing['retries'],
            'proxies': settings_outgoing['proxies'],
            'local_addresses': settings_outgoing['source_ips'],  # different because of historical reason
            'using_tor_proxy': settings_outgoing['using_tor_proxy'],
            'retry_on_http_error': None,
        }

        def new_network(network_settings: dict[str, Any], logger_name: str | None = None):
            nonlocal default_network_settings
            kwargs = {}
            kwargs.update(default_network_settings)
            kwargs.update(network_settings)
            if logger_name:
                kwargs['logger_name'] = logger_name
            return Network.from_dict(**kwargs)

        # ipv4 and ipv6 are always defined
        self.networks = {
            NetworkManager.DEFAULT_NAME: new_network({}, logger_name='default'),
            'ipv4': new_network({'local_addresses': '0.0.0.0'}, logger_name='ipv4'),
            'ipv6': new_network({'local_addresses': '::'}, logger_name='ipv6'),
        }

        # define networks from outgoing.networks. Example of configuration:
        #
        # outgoing:
        #   networks:
        #     my_proxy:
        #       proxies: http://localhost:1337
        #
        for network_name, network_dict in settings_outgoing['networks'].items():
            self.networks[network_name] = new_network(network_dict, logger_name=network_name)

        # Get the engine network settings directly from the engine modules and settings.yml (not as NetworkSettings)
        engine_network_dict_settings = {}
        for engine_spec in settings_engines:
            engine_name = engine_spec['name']
            engine = engines.get(engine_name)
            if engine is None:
                continue
            engine_network_dict_settings[engine_name] = self._get_engine_network_settings(
                engine_name, engine, default_network_settings
            )

        # Define networks from engines.[i].network (except references)
        for engine_name, network_dict in engine_network_dict_settings.items():
            if isinstance(network_dict, dict):
                self.networks[engine_name] = new_network(network_dict, logger_name=engine_name)

        # Define networks from engines.[i].network (only references)
        for engine_name, network_dict in engine_network_dict_settings.items():
            if isinstance(network_dict, str):
                self.networks[engine_name] = self.networks[network_dict]

        # The /image_proxy endpoint has a dedicated network using the same parameters
        # as the default network, but HTTP/2 is disabled. It decreases the CPU load average,
        # and the total time is more or less the same.
        if 'image_proxy' not in self.networks:
            image_proxy_params = default_network_settings.copy()
            image_proxy_params['enable_http2'] = False
            self.networks['image_proxy'] = new_network(image_proxy_params, logger_name='image_proxy')

        # Define a network the autocompletion
        if 'autocomplete' not in self.networks:
            self.networks['autocomplete'] = new_network(default_network_settings, logger_name='autocomplete')

        # Check if each network is valid:
        # * one HTTP client is instantiated
        #   --> Tor connectivity is checked if using_tor_proxy is True
        if check:
            exception_count = 0
            for network in self.networks.values():
                if not network.check_configuration():
                    exception_count += 1
            if exception_count > 0:
                raise RuntimeError("Invalid network configuration")

    @staticmethod
    def _get_engine_network_settings(engine_name, engine, default_network_settings):
        if hasattr(engine, 'network'):
            # The network configuration is defined in settings.yml inside a network key.
            # For example:
            #
            #  - name: arxiv
            #    engine: arxiv
            #    shortcut: arx
            #    network:
            #      http2: false
            #      proxies: socks5h://localhost:1337
            #
            network = getattr(engine, 'network', None)
            if not isinstance(network, (dict, str)):
                raise ValueError(f'Engine {engine_name}: network must be a dictionnary or string')
            return network
        # The network settings are mixed with the other engine settings.
        # The code checks if the keys from default_network_settings are defined in the engine module
        #
        # For example:
        #
        #  - name: arxiv
        #    engine: arxiv
        #    shortcut: arx
        #    http2: false
        #    proxies: socks5h://localhost:1337
        #
        return {
            attribute_name: getattr(engine, attribute_name)
            for attribute_name in default_network_settings.keys()
            if hasattr(engine, attribute_name)
        }


NETWORKS = NetworkManager()
"""Global :py:obj:`NetworkManager`"""
