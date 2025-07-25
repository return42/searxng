# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from ipaddress import ip_address, ip_network

import typing as t

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment

from werkzeug.middleware import proxy_fix
from werkzeug.http import parse_list_header

from . import config
from ._helpers import logger


class ProxyFix(proxy_fix.ProxyFix):

    def __init__(
        self,
        app: WSGIApplication,
        x_proto: int = 1,
        x_host: int = 0,
        x_port: int = 0,
        x_prefix: int = 0,
    ) -> None:
        self.app = app
        self.x_for: int = 1
        self.x_proto = x_proto
        self.x_host = x_host
        self.x_port = x_port
        self.x_prefix = x_prefix

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> t.Iterable[bytes]:
        cfg = config.get_global_cfg()
        trusted_proxies = cfg.get("botdetection.trusted_proxies", default=None)
        x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        x_real_ip = environ.get("HTTP_X_REAL_IP")
        logger.debug("X-Forwarded-For: %r || X-Real-IP: %r", x_forwarded_for, x_real_ip)

        if not trusted_proxies:
            logger.debug("missing configuration: botdetection.trusted_proxies / using defaults")

        elif x_forwarded_for:
            # set self.x_for from trusted_proxies
            self.x_for = 1
            x_forwarded_for = parse_list_header(x_forwarded_for)

            for proxy in reversed(x_forwarded_for):
                trust = False
                proxy = ip_address(proxy)
                for net in trusted_proxies:
                    net = ip_network(net, strict=False)
                    if proxy.version == net.version and proxy in net:
                        logger.debug("trust proxy %s (is member of %s)", proxy, net)
                        trust = True
                        break

                if trust:
                    self.x_for += 1
                else:
                    logger.debug("don't trust proxy %s", proxy)
                    break

        elif x_real_ip:
            logger.debug("X-Forwarded-For is not set, but X-Real-IP")
            x_real_ip = ip_address(x_real_ip)
            environ["REMOTE_ADDR"] = str(x_real_ip)
            self.x_for = 0

        app = super().__call__(environ, start_response)
        return app
