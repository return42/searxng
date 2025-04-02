"""Implementationsof caching solutions."""

from __future__ import annotations

from __future__ import annotations
from typing import Literal

import string
import os
import abc
import tempfile
import time
import sqlite3
import typing
import typer

from collections.abc import Generator

import msgspec

from searx import sqlitedb
from searx import logger

log = logger.getChild("cache")
app = typer.Typer()

CACHE: "ExpireCache"

def _normalize_name(name: str) -> str:
    _valid = "-_." + string.ascii_letters + string.digits
    return "".join([ c for c in name if c in _valid ] )


class ExpireCfg(msgspec.Struct):  # pylint: disable=too-few-public-methods
    """Configuration of a :py:obj:`ExpireCache` cache."""

    name: str
    """Name of the cache."""

    db_url: str = ""
    """URL of the SQLite DB, the path to the database file.  If unset a default
    DB will be created in `/tmp/sxng_cache_{self.name}.db`"""

    MAX_VALUE_LEN: int = 1024 * 10
    """Max lenght of a *serialized* value."""

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

        # if db_url is unset, use a default DB in /tmp/sxng_cache_{name}.db
        if not self.db_url:
            self.db_url = tempfile.gettempdir() + os.sep + f"sxng_cache_{_normalize_name(self.name)}.db"

class ExpireCache(abc.ABC):
    """Abstract base class for the implementation of a key/value cache
    with expire date."""

    cfg: ExpireCfg

    @abc.abstractmethod
    def set(self, key: str, value: str|int, expire: int | None) -> bool:
        """Set *key* to *value*.  To set a timeout on key use argument
        ``expire`` (in sec.).  If expire is unset the default is taken from
        :py:obj:`ExpireCfg.MAXHOLD_TIME`.  After the timeout has expired,
        the key will automatically be deleted.
        """

    @abc.abstractmethod
    def get(self, keys: str | list[str], default=None) -> str | Generator:
        """Return *value* of *key*.  If key is unset, ``None`` is returned."""

    @abc.abstractmethod
    def maintenance(self, force=False) -> bool:
        """Performs maintenance on the cache.  Force mantinance by ``force=True``
        even if the maintenance interwall is not yet reached."""



class ExpireCacheSQLite(sqlitedb.SQLiteAppl, ExpireCache):
    """Cache that manages key/value pairs in a SQLite DB.  The DB model in the
    SQLite DB is implemented using the abstract
    class :py:obj:`sqlitedb.SQLiteAppl`.

    The following configurations are required / supported:

    - :py:obj:`ExpireCfg.db_url`
    - :py:obj:`ExpireCfg.MAXHOLD_TIME`
    - :py:obj:`ExpireCfg.MAINTENANCE_PERIOD`
    - :py:obj:`ExpireCfg.MAINTENANCE_MODE`
    """

    DB_SCHEMA = 1

    # DDL_CREATE_TABLES = {
    #     "blobs": DDL_BLOBS,
    #     "blob_map": DDL_BLOB_MAP,
    # }

    def __init__(self, cfg: ExpireCfg):
        """An instance of the SQLite expire cache is build up from a
        :py:obj:`config <ExpireCfg>`."""

        self.cfg = cfg
        if cfg.db_url == ":memory:":
            logger.critical("don't use SQLite DB in :memory: in production!!")
        super().__init__(cfg.db_url)

    def create_schema(self, conn):
        """The key/value tables will be created on demand by
        :py:obj:`ExpireCacheSQLite.create_table` called from
        :py:obj:`ExpireCacheSQLite.set`.
        """
        return

    @property
    def table_names(self) -> list[str]:
        SQL_TABLE_NAMES = "SELECT name FROM sqlite_master WHERE type='table'"
        rows = self.DB.execute(SQL_TABLE_NAMES).fetchall() or []
        return [ r[0] for r in rows ]

    def create_table(self, table: str, conn: sqlite3.Connection) -> bool:
        """Creates DB ``table`` if it has not yet been created, no
        *recreates* are initiated if the table already exists.
        """
        if table in self.table_names:
            log.debug("key/value table {table} exists in DB (no need to re-create")
            return False

        log.info("key/value table {table} NOT exists in DB -> create DB table ..", )
        CREATE_TABLE = (
            f"CREATE TABLE IF NOT EXISTS {table} ("
            "     key        TEXT PRIMARY KEY,"
            "     value      val BLOB,"
            "     expire     INTEGER DEFAULT (strftime('%s', 'now') + {self.cfg.MAXHOLD_TIME})"
            ");"
            f"CREATE INDEX IF NOT EXISTS index_expire_{table} ON {table}(expire);"
            )
        conn.execute(CREATE_TABLE)

        self.properties.set(f"create_table: {table}", table)
        return True



    secret_key: str = get_setting("server.secret_key")  # type: ignore
    """By default, the value from :ref:`server.secret_key <settings server>`
    setting is used."""


    def serialize(self, value: typing.Any) -> str:
        # FIXME: encrypt / decrypt value
        # https://dnmtechs.com/efficient-string-encoding-with-password-based-encryption-in-python-3/
        return str(value)

    def deserialize(self, value: str) -> typing.Any:
        return value




    def SQL_DELETE_KEYS(self, table: str, keys: str|list[str]) -> str:
        if isinstance(keys, str):
            keys = [keys]
        if not keys:
            return ""
        key_list = "', '".join(keys)
        return f"""DELETE FROM {table} WHERE key IN ('{key_list}')"""

    def SQL_TRUNCTATE_TABLE(self, table: str) -> str:
        return f"""DELETE FROM {table} """

    @property
    def next_maintenance_time(self) -> int:
        """Returns (unix epoch) time of the next maintenance."""

        return self.cfg.MAINTENANCE_PERIOD + self.properties.m_time("LAST_MAINTENANCE")


    # implement ABC methods of ExpireCache

    def set(self, key: str, value: str|int, expire: int | None, table: str|None = None) -> bool:
        """Set key/value in ``table``.  When ``table`` argument is ``None`` (the
        default), a table name is generated from the :py:obj:`ExpireCfg.name`.

        If DB ``table`` does not exists, it will be created (on demand) by
        :py:obj:`ExpireCacheSQLite.create_table`.
        """
        if not table:
            table = _normalize_name(self.cfg.name)
        if not expire:
            expire = self.cfg.MAXHOLD_TIME
        expire = int(time.time()) + expire

        value = self.serialize(value=value)
        if len(value) > self.cfg.MAX_VALUE_LEN:
            log.warning("ExpireCache.set(): %s.key='%s' - value to big to cache (len: %s)  ", table, value, len(value))
            return False

        self.create_table(table, self.DB)

        if self.cfg.MAINTENANCE_MODE == "auto" and int(time.time()) > self.next_maintenance_time:
            # Should automatic maintenance be moved to a new thread?
            self.maintenance()

        SQL_INSERT = (
            f"INSERT INTO {table} (key, value, expire) VALUES (?, ?, ?)"
            f"    ON CONFLICT DO"
            f"UPDATE SET value=?, expire=?"
            )

        with self.connect() as conn:
            conn.execute(SQL_INSERT,(key, value, expire, value, expire))

        return True


    def get(self, keys: str | list[str], default=None) -> str|Generator:
        table: str = _normalize_name(self.cfg.name)

        fetchone = False
        if isinstance(keys, str):
            fetchone = True
            keys = [keys]

        if not keys:
            return default

        key_list = "', '".join(keys)
        SQL_SELECT_VALUE = f"SELECT value FROM {table} WHERE key IN ('{key_list}')"

        if fetchone:
            res = self.DB.execute(SQL_SELECT_VALUE).fetchone()
            if res is None:
                return default
            return self.deserialize(res[0])
        else:
            res = self.DB.execute(SQL_SELECT_VALUE).fetchall()
            if res is None:
                return default
            for row in res:
                yield self.deserialize(row[0])


    def maintenance(self, force=False) -> bool:

        # Prevent parallel DB maintenance cycles from other DB connections
        # (e.g. in multi thread or process environments).

        if not force and int(time.time()) < self.next_maintenance_time:
            logger.debug("no maintenance required yet, next maintenance interval is in the future")
            return False
        self.properties.set("LAST_MAINTENANCE", "")  # hint: this (also) sets the m_time of the property!

        table: str = _normalize_name(self.cfg.name)

        # drop items by expire time stamp ..
        expire = int(time.time())
        SQL_PURGE_EXPIRE = f"""DELETE FROM {table} WHERE expire < {expire}"""

        with self.connect() as conn:
            res = conn.execute(SQL_PURGE_EXPIRE)
            log.debug("deleted %s keys whose expiry date has been reached", res.rowcount)

        return True
