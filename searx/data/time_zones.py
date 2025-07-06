# SPDX-License-Identifier: AGPL-3.0-or-later
"""Simple implementation to store timezone data in a SQL database."""

from __future__ import annotations

__all__ = ["TimeZonesDB"]

import dataclasses
import logging
import time
import typing
import zoneinfo

from collections.abc import Generator

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


AreaTypes = typing.Literal["city_l10n", "country_l10n"]
AREATYPES: tuple[AreaTypes, ...] = typing.get_args(AreaTypes)

UNSET = object()
NOT_IN_CACHE = object()

@dataclasses.dataclass
class TimeZoneItem:
    _: dataclasses.KW_ONLY

    area_type: AreaTypes
    area_name_l10n: str
    value: typing.Any = UNSET

    # The primary keys are build up from area-type (via context) and the lower
    # case of the area-name.

    @property
    def ctx(self) -> str:
        """Create a context (a table) for each area type."""
        return f"data_timezones_{self.area_type}"

    @property
    def key(self) -> str:
        return self.area_name_l10n.lower()

    @property
    def tz_name(self):
        return self.value

    def get_value(self, default=None):
        if self.value in (UNSET, NOT_IN_CACHE):
            return self.value
        return default

    def __post_init__(self):
        if self.area_type not in AREATYPES:
            raise TypeError(f"{self.area_type} isn't of type AreaTypes")


class TimeZonesDB:
    """A database to cache and query :py:obj:`TimeZoneItem` objects."""

    def __init__(self):
        self.cache = get_cache()
        self._initialized: bool = False

    def insert(self, item: TimeZoneItem):
        """Create or update a database entry."""
        if item.value == UNSET:
            raise ValueError("Value of the TimeZoneItem has not been set.")
        self.cache.set(key=item.key, value=item.value, ctx=item.ctx , expire=None)

    def value(self, item: TimeZoneItem) -> typing.Any:
        self.init()



        tz_item = TimeZoneItem(area_type=area_type, area_name_l10n=area_name_l10n)


#        """Returns a :py:obj:`TimeZoneItem` for the given area type and name."""
# area_type: AreaTypes, area_name_l10n: str


        ctx=self.ctx_name(area_type)
        key = area_name_l10n.lower()  # search for lower case of the area name as key
        tz_name = self.cache.get(key=key, default=None, ctx=ctx)


        return TimeZoneItem(
            area_type=area_type,
            area_name_l10n=area_name_l10n,
            tz_name=tz_name
        )

    def get_items(self, area_name_l10n: str) -> list[TimeZoneItem]:
        tz_item_list = []
        for area_type in AREATYPES:
            tz_item = self.get(area_type, area_name_l10n)
            if tz_item:
                tz_item_list.append(tz_item)
        return tz_item_list

    # XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX


    def init(self):

        if self._initialized:
            return
        if self.cache.properties("TimeZoneDB loaded") != "OK":
            self.load()
            log.debug("init searx.data.TIME_ZONE: END")
            self.cache.properties.set("TimeZoneDB loaded", "OK")
            self._initialized = True
        else:
            log.debug("TimeZoneDB already loaded")

    def load(self):
        log.debug("load searx.data.TIME_ZONE: START")

        c = {"city_l10n":0, "c_country_l10n": 0}

        for area_name_l10n, area_type, tz_name in self.items_from_zoneinfo():
            self.insert(area_type, area_name_l10n, tz_name)
            c[area_type] = c[area_type] + 1

        for area_name_l10n, area_type, tz_name in self.items_from_wikidata():
            self.insert(area_type, area_name_l10n, tz_name)
            c[area_type] = c[area_type] + 1

        log.debug("load searx.data.TIME_ZONE: END %s", c)


    def items_from_zoneinfo(self) -> Generator[tuple[str, AreaTypes, str]]:

        for tz_name in zoneinfo.available_timezones():
            if not "/" in tz_name or tz_name.startswith("Etc/"):
                continue
            country_en, capital_en = tz_name.replace("_", " ").split("/", 1)

            yield country_en, "country_l10n", tz_name
            yield capital_en, "city_l10n", tz_name

    def items_from_wikidata(self) -> Generator[tuple[str, AreaTypes, str]]:

        # query l10n country names from wikidata (group by the english name of capital)
        st = time.time()
        res = wikidata_query_country_l10n()
        log.debug("init searx.data.TIME_ZONE: duration of wikidata query: %s", time.time() - st)

        if res is None:
            log.error("SPARQL_TAGS_REQUEST: wikidata query failed")

        else:
            capital_en_to_tz_name = {}
            for tz_name in zoneinfo.available_timezones():
                if not "/" in tz_name or tz_name.startswith("Etc/"):
                    continue
                capital_en = tz_name.replace("_", " ").split("/", 1)[1]
                capital_en_to_tz_name[capital_en] = tz_name

            # the l10n names of the countries from the wikipedia query
            for row in res["results"]["bindings"]:
                tz_name = capital_en_to_tz_name.get(row["capital_en"]["value"])
                if tz_name is None:
                    continue
                yield row["country_l10n"]["value"], "country_l10n", tz_name



if __name__ == "__main__":
    db = TimeZonesDB()
    for name in ["Alžírsko", "Chypre", "Grécia", "Vengrija", "Rom", "Rome"]:
        print(f"name: {name} --> timezone: {db.tz_name(name)}")
