# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parses and solves mathematical expressions.

The calculator plugin is implemented on client-side and is only available within
a web browser where JavaScript is enabled.

Here on the server side, the plugin merely manages the user settings, which
are currently limited to active/inactive."""

import typing as t

from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]

from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Calculator")
    preference_section = "query"
    description = lazy_gettext("Parses and solves mathematical expressions.")


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring

    id = "calculator"
    info_factory = Info
