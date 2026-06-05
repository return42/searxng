# SPDX-License-Identifier: AGPL-3.0-or-later
"""Simple plugin that displays information about user's request, including the
IP or HTTP User-Agent.

The information is displayed in area for the "answers".
"""

import typing as t

import re
from ipaddress import ip_address

from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]

from searx.result_types import EngineResults
from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Self Information")
    preference_section = "query"
    description = lazy_gettext(
        """Displays your IP if the query is "ip" and your user agent if the query is "user-agent"."""
    )


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring

    id = "self_info"
    keywords = ["ip", "user-agent"]
    info_factory = Info
    ip_regex = re.compile(r"^ip", re.IGNORECASE)
    ua_regex = re.compile(r"^user-agent", re.IGNORECASE)

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        """Returns a result list only for the first page."""
        res = EngineResults()

        if search.search_query.pageno > 1:
            return res

        if self.ip_regex.search(search.search_query.query) and request.remote_addr:
            l10n = lazy_gettext("Your IP is:")
            res.add(res.types.Answer(answer=f"{l10n} {ip_address(request.remote_addr).compressed}"))

        if self.ua_regex.match(search.search_query.query):
            l10n = lazy_gettext("Your user-agent is:")
            res.add(res.types.Answer(answer=f"{l10n} {request.user_agent}"))

        return res
