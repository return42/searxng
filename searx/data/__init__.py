# SPDX-License-Identifier: AGPL-3.0-or-later
"""This module holds the *data* created by::

  make data.all

"""

__all__ = [
    'ENGINE_TRAITS',
    'USER_AGENTS',
    'EXTERNAL_URLS',
    'WIKIDATA_UNITS',
    'EXTERNAL_BANGS',
    'LOCALES',
    'ahmia_blacklist_loader',
    'fetch_engine_descriptions',
    'fetch_iso4217_from_user',
    'fetch_name_from_iso4217',
    'fetch_osm_key_label',
]

import re
import unicodedata
import json
import sqlite3
from typing import Dict, List, Optional
from functools import lru_cache
from threading import local
from pathlib import Path

data_dir = Path(__file__).parent


def _load(filename):
    with open(data_dir / filename, encoding='utf-8') as f:
        return json.load(f)


def connect_ro(filename: str) -> sqlite3.Connection:
    """Return a read only SQLite connection to ``filename``.  The ``filename``
    is relative to ``searx/data``.  The caller has to close the connection
    """
    con = sqlite3.connect(f'file:{str(data_dir / filename)}?mode=ro', uri=True)
    con.executescript("pragma mmap_size = 0;")
    return con


def fetch_engine_descriptions(language) -> Dict[str, List[str]]:
    """Return engine description and source for each engine name."""

    with connect_ro("engine_descriptions.db") as con:
        res = con.execute("SELECT engine, description, source FROM engine_descriptions WHERE language=?", (language,))
        return {result[0]: [result[1], result[2]] for result in res.fetchall()}


def _normalize_name(name):
    name = name.lower().replace('-', ' ').rstrip('s')
    name = re.sub(' +', ' ', name)
    return unicodedata.normalize('NFKD', name).lower()


@lru_cache(10)
def fetch_iso4217_from_user(name: str) -> Optional[str]:

    with connect_ro("currencies.db") as con:
        # try the iso4217
        res = con.execute("SELECT iso4217 FROM currencies WHERE lower(iso4217)=? LIMIT 1", (name.lower(),))
        result = res.fetchone()
        if result:
            return result[0]

        # try the currency names
        name = _normalize_name(name)
        res = con.execute("SELECT iso4217 FROM currencies WHERE name=?", (name,))
        result = list(set(result[0] for result in res.fetchall()))
        con.close()
        if len(result) == 1:
            return result[0]

        # ambiguity --> return nothing
        return None


@lru_cache(10)
def fetch_name_from_iso4217(iso4217: str, language: str) -> Optional[str]:

    with connect_ro("currencies.db") as con:
        res = con.execute("SELECT name FROM currencies WHERE iso4217=? AND language=?", (iso4217, language))
        result = [result[0] for result in res.fetchall()]
        if len(result) == 1:
            return result[0]
        return None


@lru_cache(100)
def fetch_osm_key_label(key_name: str, language: str) -> Optional[str]:
    if key_name.startswith('currency:'):
        # currency:EUR --> get the name from the CURRENCIES variable
        # see https://wiki.openstreetmap.org/wiki/Key%3Acurrency
        # and for example https://taginfo.openstreetmap.org/keys/currency:EUR#values
        # but there is also currency=EUR (currently not handled)
        # https://taginfo.openstreetmap.org/keys/currency#values
        currency = key_name.split(':')
        if len(currency) > 1:
            label = fetch_name_from_iso4217(currency[1], language)
            if label:
                return label
            return currency[1]

    language = language.lower()
    language_short = language.split('-')[0]

    with connect_ro("osm_keys_tags.db") as con:
        res = con.execute(
            "SELECT language, label FROM osm_keys WHERE name=? AND language in (?, ?, 'en')",
            (key_name, language, language_short),
        )
        result = {result[0]: result[1] for result in res.fetchall()}
        return result.get(language) or result.get(language_short) or result.get('en')


@lru_cache(100)
def fetch_osm_tag_label(tag_key: str, tag_value: str, language: str) -> Optional[str]:
    language = language.lower()
    language_short = language.split('-')[0]
    with connect_ro("osm_keys_tags.db") as con:
        res = con.execute(
            "SELECT language, label FROM osm_tags WHERE tag_key=? AND tag_value=? AND language in (?, ?, 'en')",
            (tag_key, tag_value, language, language_short),
        )
        result = {result[0]: result[1] for result in res.fetchall()}
        return result.get(language) or result.get(language_short) or result.get('en')


def ahmia_blacklist_loader():
    """Load data from `ahmia_blacklist.txt` and return a list of MD5 values of onion
    names.  The MD5 values are fetched by::

      searxng_extra/update/update_ahmia_blacklist.py

    This function is used by :py:mod:`searx.plugins.ahmia_filter`.

    """
    with open(data_dir / 'ahmia_blacklist.txt', encoding='utf-8') as f:
        return f.read().split()


USER_AGENTS = _load('useragents.json')
EXTERNAL_URLS = _load('external_urls.json')
WIKIDATA_UNITS = _load('wikidata_units.json')
EXTERNAL_BANGS = _load('external_bangs.json')
ENGINE_TRAITS = _load('engine_traits.json')
LOCALES = _load('locales.json')
