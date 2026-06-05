# SPDX-License-Identifier: AGPL-3.0-or-later
"""Automatically loads the next page when scrolling to bottom of the current page.

The infinite-scroll plugin is implemented on client-side and is only available
within a web browser where JavaScript is enabled.

Here on the server side, the plugin merely manages the user settings, which
are currently limited to active/inactive."""

import typing as t

from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]

from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Infinite scroll")
    preference_section = "ui"
    description = lazy_gettext("Automatically loads the next page when scrolling to bottom of the current page")


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring

    id = "infiniteScroll"
    info_factory = Info
