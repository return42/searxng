# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plugin to display the current time at different timezones (usually the query
city).

The plugin uses the :py:obj:`searx.weather.GeoLocation` class, which is already
implemented in the context of weather forecasts, to determine the time zone. The
:py:obj:`searx.weather.DateTime` class is used for the localized display of date
and time.
"""

import typing as t

import datetime

from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]
from searx.result_types import EngineResults
from searx.weather import DateTime, GeoLocation

from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Timezones plugin")
    preference_section = "query"
    description = lazy_gettext("Display the current time on different time zones.")
    examples = ["time Berlin", "clock Los Angeles"]


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring

    id: str = "time_zone"
    keywords: list[str] = ["time", "timezone", "now", "clock", "timezones"]
    info_factory = Info

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:

        res = EngineResults()
        if search.search_query.pageno > 1:
            return res

        # remove keywords from the query
        query = search.search_query.query
        query_parts = filter(lambda part: part.lower() not in self.keywords, query.split(" "))
        search_term = " ".join(query_parts).strip()

        if not search_term:
            date_time = DateTime(datetime.datetime.now())
            res.add(res.types.Answer(answer=date_time.l10n()))
            return res

        geo = GeoLocation.by_query(search_term=search_term)
        if geo:
            date_time = DateTime(datetime.datetime.now(tz=geo.zoneinfo))
            tz_name = geo.timezone.replace('_', ' ')
            res.add(res.types.Answer(answer=f"{tz_name}:" f" {date_time.l10n()} ({date_time.datetime.strftime('%Z')})"))

        return res
