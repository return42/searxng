# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, missing-class-docstring

from __future__ import annotations
import typing

import zoneinfo
import datetime

from flask_babel import gettext
from searx.result_types import EngineResults
from searx.data import TIME_ZONES

from . import Plugin, PluginInfo

if typing.TYPE_CHECKING:
    import flask
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.plugins import PluginCfg


datetime_format = "%H:%M - %A, %d/%m/%y"


class SXNGPlugin(Plugin):

    id = "time_zone"
    keywords = ["time", "timezone", "now", "clock", "timezones"]

    def __init__(self, plg_cfg: "PluginCfg"):
        super().__init__(plg_cfg)

        self.info = PluginInfo(
            id=self.id,
            name=gettext("Timezones plugin"),
            description=gettext("Display the current time on different time zones."),
            preference_section="query",
            examples=["time Berlin", "clock Los Angeles"],
        )

    def init(self, app: "flask.Flask") -> bool:  # pylint: disable=unused-argument
        TIME_ZONES.init()
        return True

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        results = EngineResults()

        if search.search_query.pageno > 1:
            return results

        # remove keywords from the query
        query = search.search_query.query
        query_parts = filter(lambda part: part.lower() not in self.keywords, query.split(" "))
        location = " ".join(query_parts)

        if not location:
            results.add(results.types.Answer(answer=f"{datetime.datetime.now().strftime(datetime_format)}"))
            return results

        tz_name = TIME_ZONES.tz_info(location)
        if tz_name:
            import pdb
            pdb.set_trace()
            zone = zoneinfo.ZoneInfo(tz_name)
            now = datetime.datetime.now(tz=zone)

            results.add(
                results.types.Answer(
                    answer=f"{now.strftime(datetime_format)} at {tz_name.replace('_', ' ')} ({now.strftime('%Z')})"
                )
            )

        return results
