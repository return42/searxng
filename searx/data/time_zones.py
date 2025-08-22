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

from searx.cache import ExpireCacheSQLite


def wikidata_query_country_l10n() -> Generator[dict[str, dict[str, str]]]:
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

    _st = time.time()
    response = wikidata.send_wikidata_query(sparql, timeout=60)  # type: ignore
    log.debug("init searx.data.TIME_ZONE: duration of wikidata query: %s", time.time() - _st)
    if response is not None:
        yield from response["results"]["bindings"]


AreaTypes = typing.Literal["city_l10n", "country_l10n"]
"""Type of the area (country or city)"""
AREATYPES: tuple[AreaTypes, ...] = typing.get_args(AreaTypes)

# UNSET = object()
# NOT_IN_CACHE = object()


@dataclasses.dataclass
class TimeZoneItem:
    """A ``TimeZoneItem`` in the database defines an area (country or city) and
    assigns a time zone to it.  For each area type (:py:obj:`AreaTypes`) a
    separate DB table is created in the DB (one table for countries, one for
    cities).

    """

    _: dataclasses.KW_ONLY

    area_type: AreaTypes
    area_name_l10n: str
    """Name of the region (area)."""
    tz_name: str
    """Name of the time zone"""

    @property
    def table(self) -> str:
        """Create a context (a table) for each area type."""
        return self.area_type

    # The primary keys are build up from area-type (via context) and the lower
    # case of the area-name.  This also avoids name collisions, for example if a
    # capital city has the same name as a country.

    @property
    def key(self) -> str:
        return self.area_name_l10n.lower()

    @property
    def value(self):
        return self.tz_name

    def __post_init__(self):
        if self.area_type not in AREATYPES:
            raise TypeError(f"{self.area_type} isn't of type AreaTypes")

    @property
    def zoneinfo(self) -> zoneinfo.ZoneInfo:
        return zoneinfo.ZoneInfo(self.tz_name)


class TimeZonesDB:
    """A database to cache and query :py:obj:`TimeZoneItem` objects."""

    def __init__(self):
        self.cache: ExpireCacheSQLite = get_cache()
        self._initialized: bool = False

    def ctx(self, area_type: str):
        return f"data_timezones_{area_type}"

    def init(self):
        if self.cache.properties("TimeZoneDB loaded") != "OK":
            # To avoid parallel initialization, the property is set first
            self.cache.properties.set("TimeZoneDB loaded", "OK")
            self.load()
            log.debug("init searx.data.TIME_ZONE: END")
        # F I X M E:
        #     do we need a maintenance .. remember: database is stored
        #     in /tmp and will be rebuild during the reboot anyway

    def load(self):
        c = {"city_l10n": 0, "country_l10n": 0}

        for tz_item in self.load_from_zoneinfo():
            self.insert(tz_item)
            c[tz_item.area_type] = c[tz_item.area_type] + 1

        for tz_item in self.load_from_wikidata():
            self.insert(tz_item)
            c[tz_item.area_type] = c[tz_item.area_type] + 1

    @staticmethod
    def load_from_zoneinfo() -> Generator[TimeZoneItem]:

        for tz_name in zoneinfo.available_timezones():
            if not "/" in tz_name or tz_name.startswith("Etc/"):
                continue
            country_en, capital_en = tz_name.replace("_", " ").split("/", 1)

            yield TimeZoneItem(area_type="country_l10n", area_name_l10n=country_en, tz_name=tz_name)
            yield TimeZoneItem(area_type="city_l10n", area_name_l10n=capital_en, tz_name=tz_name)

    @staticmethod
    def load_from_wikidata() -> Generator[TimeZoneItem]:

        capital_en_to_tz_name: dict[str, str] = {}
        for tz_name in zoneinfo.available_timezones():
            if not "/" in tz_name or tz_name.startswith("Etc/"):
                continue
            capital_en = tz_name.replace("_", " ").split("/", 1)[1]
            capital_en_to_tz_name[capital_en] = tz_name

        for result in wikidata_query_country_l10n():
            capital_en: str = result["capital_en"]["value"]
            area_name_l10n: str = result["country_l10n"]["value"]

            # It's a false assumption that the time zone of a city is always the
            # same as the time zone of the capital of that city's country.
            tz_name = capital_en_to_tz_name.get(capital_en)
            if not tz_name:
                continue
            print(f"country_l10n -- {area_name_l10n} -- {tz_name}")
            yield TimeZoneItem(area_type="country_l10n", area_name_l10n=area_name_l10n, tz_name=tz_name)

    def insert(self, tz_item: TimeZoneItem) -> bool:
        """Create or update a database entry."""
        return self.cache.set(
            key=tz_item.key,
            value=tz_item.value,
            ctx=self.ctx(tz_item.table),
            expire=None,
        )

    def get_tz_items(self, area_name_l10n: str) -> list[TimeZoneItem]:
        self.init()
        tz_item_list: list[TimeZoneItem] = []
        for area_type in AREATYPES:
            value: str | None = self.cache.get(key=area_name_l10n.lower(), ctx=self.ctx(area_type))
            if not value:
                continue
            tz_item_list.append(
                TimeZoneItem(
                    area_type=area_type,
                    area_name_l10n=area_name_l10n,
                    tz_name=value,
                )
            )
        return tz_item_list


if __name__ == "__main__":
    _db = TimeZonesDB()
    for _name in ["Alžírsko", "Dreamland", "Chypre", "Grécia", "Vengrija", "Rom", "Rome"]:
        print(f"{_name}:")
        for _tz_item in _db.get_tz_items(area_name_l10n=_name):
            print(f"  --> timezone: {_tz_item.value}")
