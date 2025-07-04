# SPDX-License-Identifier: AGPL-3.0-or-later
"""Simple implementation to store timezone data in a SQL database."""

from __future__ import annotations

__all__ = ["TimeZonesDB"]

import time
import typing
import zoneinfo
import logging

from searx.data.core import get_cache, log


def wikidata_query_country_l10n():
    # pylint: disable=import-outside-toplevel, cyclic-import
    # avoid circular imports
    from searx.locales import LOCALE_NAMES, locales_initialize

    locales_initialize()
    from searx.engines import wikidata

    # monkey patch wikidata py-module
    wikidata.logger = logging.getLogger("searx.engines.wikidata")

    languages_sparql = ', '.join(set(map(lambda l: repr(l.split('_')[0]), LOCALE_NAMES.keys())))

    sparql = (
        """\
SELECT
  ?country_l10n                           # localized country name
  ?capital_en                             # one (arbitrary "first") capital name (in english)
WHERE {
  ?item wdt:P36  ?capital ;               # capital(s)
        wdt:P31  wd:Q3624078 ;            # sovereign state
        rdfs:label ?country_l10n .
  ?capital rdfs:label ?capital_en .
  FILTER ( LANG(?capital_en) = "en" ).
  FILTER ( LANG(?country_l10n) IN ("""
        + languages_sparql
        + """)).
  MINUS {                                 # exclude defunct states
    ?item wdt:P31 wd:Q3024240 .
  }
}
GROUP BY ?country_l10n ?capital_en
ORDER BY ?item ?country_l10n"""
    )

    res = wikidata.send_wikidata_query(sparql, timeout=30)
    return res


ZoneType = tuple[str, typing.Literal["city_l10n", "country_l10n"], str]


class TimeZonesDB:
    # pylint: disable=missing-class-docstring,invalid-name

    ctx_name = "data_timezones"

    def __init__(self):
        self.cache = get_cache()
        self._initialized = False

    def init(self):
        if self._initialized:
            return

        if self.cache.properties("TimeZoneDB loaded") != "OK":
            self.load()
            self.cache.properties.set("TimeZoneDB loaded", "OK")
        # F I X M E:
        #     do we need a maintenance .. rember: database is stored
        #     in /tmp and will be rebuild during the reboot anyway
        self._initialized = True

    def load(self):
        log.debug("init searx.data.TIME_ZONE")

        # insert the English names of the capital cities into the database
        capital_en_to_tz = {}
        for tz in zoneinfo.available_timezones():
            if not "/" in tz or tz.startswith("Etc/"):
                continue
            country_en, capital_en = tz.replace("_", " ").split("/", 1)
            capital_en_to_tz[capital_en] = tz
            self.add(capital_en, "city_l10n", tz)
            self.add(country_en, "country_l10n", tz)

        # query l10n country names from wikidata (group by the english name of capital)
        st = time.time()
        res = wikidata_query_country_l10n()
        log.error("duration of wikidata query: %s", time.time() - st)

        if res is None:
            log.error("SPARQL_TAGS_REQUEST: wikidata query failed")
            return

        # insert the l10n names of the countries from the wikipedia query
        for row in res["results"]["bindings"]:
            tz = capital_en_to_tz.get(row["capital_en"]["value"])
            if tz is None:
                continue
            self.add(row["country_l10n"]["value"], "country_l10n", tz)

    def add(self, area_name_l10n: str, area_type: typing.Literal["city_l10n", "country_l10n"], timezone: str):
        self.cache.set(
            key=area_name_l10n.lower(),
            value=(area_type, timezone),
            ctx=self.ctx_name,
            expire=None,
        )

    def get(self, area_name_l10n: str) -> str | None:
        self.init()
        return self.cache.get(key=area_name_l10n.lower(), default=None, ctx=self.ctx_name)


if __name__ == "__main__":
    db = TimeZonesDB()
    for name in ["Alžírsko", "Chypre", "Grécia", "Vengrija", "Rom", "Rome"]:
        print(f"name: {name} --> timezone: {db.get(name)}")
