# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, missing-class-docstring

from __future__ import annotations
import typing as t

import datetime

from flask_babel import gettext  # type: ignore
from searx.result_types import EngineResults
from searx.data import TIME_ZONES
from searx.weather import DateTime

from . import Plugin, PluginInfo

if t.TYPE_CHECKING:
    import flask
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.plugins import PluginCfg


@t.final
class SXNGPlugin(Plugin):

    id: str = "time_zone"
    keywords: list[str] = ["time", "timezone", "now", "clock", "timezones"]

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
        area_name_l10n = " ".join(query_parts)

        if not area_name_l10n:
            date_time = DateTime(time=datetime.datetime.now())
            results.add(results.types.Answer(answer=date_time.l10n()))
            return results

        for tz_item in TIME_ZONES.get_tz_items(area_name_l10n):
            date_time = DateTime(time=datetime.datetime.now(tz=tz_item.zoneinfo))
            results.add(
                results.types.Answer(
                    answer=(
                        f"{tz_item.tz_name.replace('_', ' ')}:"
                        f" {date_time.l10n()} ({date_time.datetime.strftime('%Z')})"
                    )
                )
            )

        return results
