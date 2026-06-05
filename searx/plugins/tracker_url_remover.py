# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remove trackers arguments from the returned URL.

The :py:obj:`tracker patterns <data.tracker_patterns>` are obtained from
SearXNG's built-in DB.
"""

import logging
import typing as t

import flask
from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]

from searx.data import TRACKER_PATTERNS

from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.result_types import Result, LegacyResult  # type: ignore[reportPrivateLocalImportUsage]


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Tracker URL remover")
    preference_section = "privacy"
    description = lazy_gettext("Remove trackers arguments from the returned URL")


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring, unused-argument

    id = "tracker_url_remover"
    info_factory = Info
    log = logging.getLogger("searx.plugins.tracker_url_remover")

    def init_from_app(self, app: flask.Flask) -> bool:
        if not super().init_from_app(app=app):
            return False
        TRACKER_PATTERNS.init()
        return True

    def on_result(self, request: "SXNG_Request", search: "SearchWithPlugins", result: "Result") -> bool:

        result.filter_urls(self.filter_url_field)
        return True

    @classmethod
    def filter_url_field(
        cls,
        result: "Result|LegacyResult",  # type: ignore[reportUnusedParameter]
        field_name: str,
        url_src: str,
    ) -> bool | str:
        """Returns bool ``True`` to use URL unchanged (``False`` to ignore URL).
        If URL should be modified, the returned string is the new URL to use."""

        if not url_src:
            cls.log.debug("missing a URL in field %s", field_name)
            return True

        return TRACKER_PATTERNS.clean_url(url=url_src)
