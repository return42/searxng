# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from collections import abc
from ipaddress import ip_address, ip_network
from werkzeug.middleware import proxy_fix
from werkzeug.http import parse_list_header

import typing as t

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment


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
        x_for = 1
        super().__init__(app, x_for, x_proto, x_host, x_port,x_prefix)

    def __call__(self, environ: WSGIEnvironment, start_response: StartResponse) -> abc.Iterable[bytes]:
        cfg = config.get_global_cfg()
        trusted_proxies = cfg.get("botdetection.trusted_proxies", default=None)
        x_forwarded_for = environ.get("HTTP_X_FORWARDED_FOR")
        x_real_ip = environ.get("HTTP_X_REAL_IP")
        logger.debug("X-Forwarded-For: %r || X-Real-IP: %r", x_forwarded_for, x_real_ip)

        if not trusted_proxies:
            logger.debug("missing configuration: botdetection.trusted_proxies / using defaults")

        elif x_forwarded_for:
            # curl -H "X-Forwarded-For: 203.0.113.195, ::ffff:127.0.0.1, 127.0.0.3"

            # set self.x_for from trusted_proxies
            self.x_for = 1
            x_forwarded_for = parse_list_header(x_forwarded_for)

            for proxy in reversed(x_forwarded_for):
                trust = False
                proxy = ip_address(proxy)
                if proxy.version == 6 and proxy.ipv4_mapped:
                    proxy = proxy.ipv4_mapped
                for net in trusted_proxies:
                    net = ip_network(net, strict=False)
                    if proxy.version == net.version and proxy in net:
                        logger.debug("trust proxy %s (member of %s)", proxy, net)
                        trust = True
                        break

                if trust:
                    self.x_for += 1
                else:
                    break
            logger.debug("X-Forwarded-For (x_for=%s)", self.x_for)

        elif x_real_ip:
            # curl -H "X-Real-ip: 7.8.9.0" http://127.0.0.1:8888/
            logger.debug("X-Forwarded-For is not set, but X-Real-IP")
            x_real_ip = ip_address(x_real_ip)
            environ["REMOTE_ADDR"] = str(x_real_ip)
            self.x_for = 0

        app = super().__call__(environ, start_response)
        logger.debug("final REMOTE_ADDR is: %s", environ["REMOTE_ADDR"])
        return app
