"""Implementationsof caching solutions."""

from __future__ import annotations

from __future__ import annotations
from typing import Literal

import string
import os
import abc
import dataclasses
import hashlib
import logging
import sqlite3
import tempfile
import time
import typer

import msgspec

from searx import sqlitedb
from searx import logger

log = logger.getChild("cache")
app = typer.Typer()

CACHE: "ExpireCache"

class ExpireCfg(msgspec.Struct):  # pylint: disable=too-few-public-methods
    """Configuration of a :py:obj:`ExpireCache` cache."""

    name: str
    """Name of the cache."""

    db_url: str = ""
    """URL of the SQLite DB, the path to the database file.  If unset a default
    DB will be created in `/tmp/sxng_cache_{self.name}.db`"""

    MAXHOLD_TIME: int = 60 * 60 * 24 * 7  # 7 days
    """Hold time (default in sec.), after which a value is removed from the cache."""

    MAINTENANCE_PERIOD: int = 60 * 60
    """Maintenance period in seconds / when :py:obj:`MAINTENANCE_MODE` is set to
    ``auto``."""

    MAINTENANCE_MODE: Literal["auto", "off"] = "auto"
    """Type of maintenance mode

    ``auto``:
      Maintenance is carried out automatically as part of the maintenance
      intervals (:py:obj:`MAINTENANCE_PERIOD`); no external process is required.

    ``off``:
      Maintenance is switched off and must be carried out by an external process
      if required.
    """

    def __post_init__(self):

        # if db_url is unset, use a default DB in /tmp/sxng_cache_{self.name}.db
        if not self.db_url:
            _valid = "-_.()" + string.ascii_letters + string.digits
            db_fname = "".join([ c for c in self.name if c in _valid ] )
            self.db_url = tempfile.gettempdir() + os.sep + f"sxng_cache_{self.name}.db"

class ExpireCache(abc.ABC):
    """Abstract base class for the implementation of a key/value cache
    with expire date."""

    @abc.abstractmethod
    def __init__(self, cfg: ExpireCfg):
        """An instance of the cache is build up from the configuration."""

    @abc.abstractmethod
    def set(self, key: str, value: str|int, expire: int | None) -> bool:
        """Set *key* to *value*.  To set a timeout on key use argument
        ``expire`` (in sec.).  If expire is unset the default is taken from
        :py:obj:`ExpireCfg.MAXHOLD_TIME`.  After the timeout has expired,
        the key will automatically be deleted.
        """

    @abc.abstractmethod
    def get(self, key: str) -> str | int | None:
        """Return *value* of *key*.  If key is unset, ``None`` is returned."""


    @abc.abstractmethod
    def maintenance(self, force=False):
        """Performs maintenance on the cache"""



class ExpireCacheSQLite(sqlitedb.SQLiteAppl, ExpireCache):
    """



    Favicon cache that manages the favicon BLOBs in a SQLite DB.  The DB
    model in the SQLite DB is implemented using the abstract class
    :py:obj:`sqlitedb.SQLiteAppl`.

    The following configurations are required / supported:

    - :py:obj:`FaviconCacheConfig.db_url`
    - :py:obj:`FaviconCacheConfig.HOLD_TIME`
    - :py:obj:`FaviconCacheConfig.LIMIT_TOTAL_BYTES`
    - :py:obj:`FaviconCacheConfig.BLOB_MAX_BYTES`
    - :py:obj:`MAINTENANCE_PERIOD`
    - :py:obj:`MAINTENANCE_MODE`
    """

    DB_SCHEMA = 1

    DDL_BLOBS = """\
CREATE TABLE IF NOT EXISTS blobs (
  sha256     TEXT,
  bytes_c    INTEGER,
  mime       TEXT NOT NULL,
  data       BLOB NOT NULL,
  PRIMARY KEY (sha256))"""

    """Table to store BLOB objects by their sha256 hash values."""

    DDL_BLOB_MAP = """\
CREATE TABLE IF NOT EXISTS blob_map (
    m_time     INTEGER DEFAULT (strftime('%s', 'now')),  -- last modified (unix epoch) time in sec.
    sha256     TEXT,
    resolver   TEXT,
    authority  TEXT,
    PRIMARY KEY (resolver, authority))"""

    """Table to map from (resolver, authority) to sha256 hash values."""

    DDL_CREATE_TABLES = {
        "blobs": DDL_BLOBS,
        "blob_map": DDL_BLOB_MAP,
    }

    SQL_DROP_LEFTOVER_BLOBS = (
        "DELETE FROM blobs WHERE sha256 IN ("
        " SELECT b.sha256"
        "   FROM blobs b"
        "   LEFT JOIN blob_map bm"
        "     ON b.sha256 = bm.sha256"
        "  WHERE bm.sha256 IS NULL)"
    )
    """Delete blobs.sha256 (BLOBs) no longer in blob_map.sha256."""

    SQL_ITER_BLOBS_SHA256_BYTES_C = (
        "SELECT b.sha256, b.bytes_c FROM blobs b"
        "  JOIN blob_map bm "
        "    ON b.sha256 = bm.sha256"
        " ORDER BY bm.m_time ASC"
    )

    SQL_INSERT_BLOBS = (
        "INSERT INTO blobs (sha256, bytes_c, mime, data) VALUES (?, ?, ?, ?)"
        "    ON CONFLICT (sha256) DO NOTHING"
    )  # fmt: skip

    SQL_INSERT_BLOB_MAP = (
        "INSERT INTO blob_map (sha256, resolver, authority) VALUES (?, ?, ?)"
        "    ON CONFLICT DO UPDATE "
        "   SET sha256=excluded.sha256, m_time=strftime('%s', 'now')"
    )

    def __init__(self, cfg: FaviconCacheConfig):
        """An instance of the favicon cache is build up from the configuration."""  #

        if cfg.db_url == ":memory:":
            logger.critical("don't use SQLite DB in :memory: in production!!")
        super().__init__(cfg.db_url)
        self.cfg = cfg

    def __call__(self, resolver: str, authority: str) -> None | tuple[None | bytes, None | str]:

        sql = "SELECT sha256 FROM blob_map WHERE resolver = ? AND authority = ?"
        res = self.DB.execute(sql, (resolver, authority)).fetchone()
        if res is None:
            return None

        data, mime = (None, None)
        sha256 = res[0]
        if sha256 == FALLBACK_ICON:
            return data, mime

        sql = "SELECT data, mime FROM blobs WHERE sha256 = ?"
        res = self.DB.execute(sql, (sha256,)).fetchone()
        if res is not None:
            data, mime = res
        return data, mime

    def set(self, resolver: str, authority: str, mime: str | None, data: bytes | None) -> bool:

        if self.cfg.MAINTENANCE_MODE == "auto" and int(time.time()) > self.next_maintenance_time:
            # Should automatic maintenance be moved to a new thread?
            self.maintenance()

        if data is not None and mime is None:
            logger.error(
                "favicon resolver %s tries to cache mime-type None for authority %s",
                resolver,
                authority,
            )
            return False

        bytes_c = len(data or b"")
        if bytes_c > self.cfg.BLOB_MAX_BYTES:
            logger.info(
                "favicon of resolver: %s / authority: %s to big to cache (bytes: %s) " % (resolver, authority, bytes_c)
            )
            return False

        if data is None:
            sha256 = FALLBACK_ICON
        else:
            sha256 = hashlib.sha256(data).hexdigest()

        with self.connect() as conn:
            if sha256 != FALLBACK_ICON:
                conn.execute(self.SQL_INSERT_BLOBS, (sha256, bytes_c, mime, data))
            conn.execute(self.SQL_INSERT_BLOB_MAP, (sha256, resolver, authority))

        return True

    @property
    def next_maintenance_time(self) -> int:
        """Returns (unix epoch) time of the next maintenance."""

        return self.cfg.MAINTENANCE_PERIOD + self.properties.m_time("LAST_MAINTENANCE")

    def maintenance(self, force=False):

        # Prevent parallel DB maintenance cycles from other DB connections
        # (e.g. in multi thread or process environments).

        if not force and int(time.time()) < self.next_maintenance_time:
            logger.debug("no maintenance required yet, next maintenance interval is in the future")
            return
        self.properties.set("LAST_MAINTENANCE", "")  # hint: this (also) sets the m_time of the property!

        # do maintenance tasks

        with self.connect() as conn:

            # drop items not in HOLD time
            res = conn.execute(
                f"DELETE FROM blob_map"
                f" WHERE cast(m_time as integer) < cast(strftime('%s', 'now') as integer) - {self.cfg.HOLD_TIME}"
            )
            logger.debug("dropped %s obsolete blob_map items from db", res.rowcount)
            res = conn.execute(self.SQL_DROP_LEFTOVER_BLOBS)
            logger.debug("dropped %s obsolete BLOBS from db", res.rowcount)

            # drop old items to be in LIMIT_TOTAL_BYTES
            total_bytes = conn.execute("SELECT SUM(bytes_c) FROM blobs").fetchone()[0] or 0
            if total_bytes > self.cfg.LIMIT_TOTAL_BYTES:

                x = total_bytes - self.cfg.LIMIT_TOTAL_BYTES
                c = 0
                sha_list = []
                for row in conn.execute(self.SQL_ITER_BLOBS_SHA256_BYTES_C):
                    sha256, bytes_c = row
                    sha_list.append(sha256)
                    c += bytes_c
                    if c > x:
                        break
                if sha_list:
                    conn.execute("DELETE FROM blobs WHERE sha256 IN ('%s')" % "','".join(sha_list))
                    conn.execute("DELETE FROM blob_map WHERE sha256 IN ('%s')" % "','".join(sha_list))
                    logger.debug("dropped %s blobs with total size of %s bytes", len(sha_list), c)

    def _query_val(self, sql, default=None):
        val = self.DB.execute(sql).fetchone()
        if val is not None:
            val = val[0]
        if val is None:
            val = default
        return val

    def state(self) -> FaviconCacheStats:
        return FaviconCacheStats(
            favicons=self._query_val("SELECT count(*) FROM blobs", 0),
            bytes=self._query_val("SELECT SUM(bytes_c) FROM blobs", 0),
            domains=self._query_val("SELECT count(*) FROM (SELECT authority FROM blob_map GROUP BY authority)", 0),
            resolvers=self._query_val("SELECT count(*) FROM (SELECT resolver FROM blob_map GROUP BY resolver)", 0),
        )
