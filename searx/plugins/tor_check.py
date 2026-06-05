# SPDX-License-Identifier: AGPL-3.0-or-later
"""A plugin to check if the ip address of the request is a Tor exit-node if the
user searches for ``tor-check``.

It fetches the tor exit node list from :py:obj:`url_exit_list` and parses all
the IPs into a list, then checks if the user's IP address is in it.
"""

from ipaddress import ip_address
import typing as t

import re
from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]
from httpx import HTTPError

from searx.network import get
from searx.result_types import EngineResults
from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request


# Regex for exit node addresses in the list.
reg = re.compile(r"(?<=ExitAddress )\S+")

url_exit_list = "https://check.torproject.org/exit-addresses"
"""URL to load Tor exit list from."""


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Tor check plugin")
    preference_section = "query"
    description = lazy_gettext(
        "This plugin checks if the address of the request is a Tor exit-node, and"
        " informs the user if it is; like check.torproject.org, but from SearXNG."
    )


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring

    id = "tor_check"
    keywords = ["tor-check", "tor_check", "torcheck", "tor", "tor check"]
    info_factory = Info

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        res = EngineResults()

        if search.search_query.pageno > 1:
            return res

        if search.search_query.query.lower() in self.keywords:

            # Request the list of tor exit nodes.
            try:
                resp = get(url_exit_list)
                node_list = re.findall(reg, resp.text)

            except HTTPError:
                # No answer, return error
                msg = lazy_gettext("Could not download the list of Tor exit-nodes from")
                res.add(res.types.Answer(answer=f"{msg} {url_exit_list}"))
                return res

            real_ip = ip_address(address=str(request.remote_addr)).compressed

            if real_ip in node_list:
                msg = lazy_gettext("You are using Tor and it looks like you have the external IP address")
                res.add(res.types.Answer(answer=f"{msg} {real_ip}"))

            else:
                msg = lazy_gettext("You are not using Tor and you have the external IP address")
                res.add(res.types.Answer(answer=f"{msg} {real_ip}"))

        return res
