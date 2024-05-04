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
    'OSM_KEYS_TAGS',
    'LOCALES',
    'ahmia_blacklist_loader',
    'fetch_engine_descriptions',
    'fetch_iso4217_from_user',
    'fetch_name_from_iso4217',
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
data_connection_local = local()


def _load(filename):
    with open(data_dir / filename, encoding='utf-8') as f:
        return json.load(f)


def _get_connection(filename: str) -> sqlite3.Connection:
    """Return a read only SQLite connection to filename.
    The filename is relative to searx/data

    Multiple calls to this function in the same thread,
    already return the same connection.
    """
    connection = data_connection_local.__dict__.get(filename)
    if connection is not None:
        return connection

    data_filename = str(data_dir / filename)
    # open database in read only mode
    data_connection = sqlite3.connect(f'file:{data_filename}?mode=ro', uri=True)

    data_connection_local.__dict__[filename] = data_connection
    return data_connection


def fetch_engine_descriptions(language) -> Dict[str, List[str]]:
    """Return engine description and source for each engine name."""
    res = _get_connection("engine_descriptions.db").execute(
        "SELECT engine, description, source FROM engine_descriptions WHERE language=?", (language,)
    )
    return {result[0]: [result[1], result[2]] for result in res.fetchall()}


def _normalize_name(name):
    name = name.lower().replace('-', ' ').rstrip('s')
    name = re.sub(' +', ' ', name)
    return unicodedata.normalize('NFKD', name).lower()


@lru_cache(10)
def fetch_iso4217_from_user(name: str) -> Optional[str]:
    connection = _get_connection("currencies.db")

    # try the iso4217
    res = connection.execute("SELECT iso4217 FROM currencies WHERE lower(iso4217)=? LIMIT 1", (name.lower(),))
    result = res.fetchone()
    if result:
        return result[0]

    # try the currency names
    name = _normalize_name(name)
    res = connection.execute("SELECT iso4217 FROM currencies WHERE name=?", (name,))
    result = list(set(result[0] for result in res.fetchall()))
    if len(result) == 1:
        return result[0]

    # ambiguity --> return nothing
    return None


@lru_cache(10)
def fetch_name_from_iso4217(iso4217: str, language: str) -> Optional[str]:
    res = _get_connection("currencies.db").execute(
        "SELECT name FROM currencies WHERE iso4217=? AND language=?", (iso4217, language)
    )
    result = [result[0] for result in res.fetchall()]
    if len(result) == 1:
        return result[0]
    return None


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
OSM_KEYS_TAGS = _load('osm_keys_tags.json')
ENGINE_TRAITS = _load('engine_traits.json')
LOCALES = _load('locales.json')
