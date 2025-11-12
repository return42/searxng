# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!! [POC:SideCar]"""

import typing as t
import random
import time
import msgspec

from searx import logger
from searx.cache import ExpireCacheSQLite, ExpireCacheCfg
from searx.sidecar_pkg.web_session import WebSession

if t.TYPE_CHECKING:
    from searx.sidecar_pkg.types import SessionType

log = logger.getChild("sidecar.cache")


class WebSessionCache:
    """Mixin class for the cache of the SideCar infrastructure in SearXNG.

    The WebSessionCache mixin allows to store a list of :py:obj:`WebSession`
    objects.  The value for the primary key at the SQL DB level is generated
    using the following template::

        f"/session_type={session.ctx.session_type}/session_uuid={session.uuid}/"
    """

    def session_push(self, session: "WebSession"):
        cache = t.cast(SideCarCache, self)

        key = f"/session_type={session.ctx.session_type}/session_uuid={session.uuid}/"
        expire = session.validity_sec - int(time.time() - session.time_created)
        if expire <= 0:
            raise ValueError(f"{session.ctx.session_type} session {session.uuid} has already expired.")

        json_str = msgspec.json.encode(session).decode("utf-8")
        log.debug("SideCarCache.session_push: %s : %s", key, json_str)
        cache.set(key=key, value=json_str, ctx="WebSession", expire=expire)  # pylint: disable=no-member

    def session_get(self, session_type: "SessionType") -> WebSession | None:
        cache = t.cast(SideCarCache, self)
        cache.maintenance()  # pylint: disable=no-member

        table = "WebSession"
        if table not in cache.table_names:  # pylint: disable=no-member
            return None

        sql = f"SELECT value FROM {table} WHERE key LIKE '%/session_type={session_type}/%'"
        rows = cache.DB.execute(sql).fetchall() or []  # pylint: disable=no-member
        if not rows:
            return None

        row = random.choice(rows)
        json_str: str = cache.deserialize(row[0])  # pylint: disable=no-member
        session: WebSession = msgspec.json.decode(json_str, type=WebSession)
        log.debug("SideCarCache.session_get: %s (1/%s) uuid: %s", session_type, len(rows), session.uuid)
        return session


class SideCarCache(WebSessionCache, ExpireCacheSQLite):
    """SideCar's cache in a running SearXNG instance."""

    DB_SCHEMA: int = 20251109  # ToDo: update schema version on every schema modification

    def __init__(self):
        cfg = ExpireCacheCfg(
            name="SXNG_SIDECAR_CACHE",
            MAXHOLD_TIME=60 * 60 * 24 * 7,  # 7 days
            MAINTENANCE_PERIOD=60 * 5,  # 5min
        )

        super().__init__(cfg)


CACHE = SideCarCache()
"""Global :py:obj:`searx.cache.ExpireCacheSQLite` instance to cache objects from
sidecar tasks. The `MAXHOLD_TIME` is 7 days and the `MAINTENANCE_PERIOD` is set
to 5 minutes."""
