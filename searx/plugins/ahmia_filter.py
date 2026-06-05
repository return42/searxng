# SPDX-License-Identifier: AGPL-3.0-or-later
"""Filter out onion results that appear in `Ahmia's blacklist`_.

Ahmia blocks websites that contain child sexual abuse material. You can use this
to filter child sexual abuse material from your own search. Onion addresses are
masked by creating an MD5 sum of the onion domain.

.. _Ahmia's blacklist: https://ahmia.fi/blacklist
"""
# pylint: disable=missing-class-docstring

import typing as t
from hashlib import md5

import flask
from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]

from searx.data import ahmia_blacklist_loader
from searx import get_setting

from searx.plugins import Plugin, PluginInfo, PluginCfg

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.result_types import Result

ahmia_blacklist: list[str] = []


@t.final
class Info(PluginInfo):
    name = lazy_gettext("Ahmia blacklist")
    preference_section = "general"
    description = lazy_gettext("Filter out onion results that appear in Ahmia's blacklist.")


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg]):

    id = "ahmia_filter"
    info_factory = Info

    def init_from_app(self, app: flask.Flask) -> bool:  # pylint: disable=unused-argument
        global ahmia_blacklist  # pylint: disable=global-statement

        if not super().init_from_app(app=app):
            return False

        if not get_setting("outgoing.using_tor_proxy"):
            # disable the plugin
            return False
        ahmia_blacklist = ahmia_blacklist_loader()
        return True

    def on_result(
        self, request: "SXNG_Request", search: "SearchWithPlugins", result: "Result"
    ) -> bool:  # pylint: disable=unused-argument
        if not getattr(result, "is_onion", False) or not getattr(result, "parsed_url", False):
            return True
        result_hash = md5(result["parsed_url"].hostname.encode()).hexdigest()
        return result_hash not in ahmia_blacklist
