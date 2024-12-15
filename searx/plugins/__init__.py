# SPDX-License-Identifier: AGPL-3.0-or-later
"""

ToDo: needs some documentation ..

"""

from __future__ import annotations

__all__ = ["PluginInfo", "Plugin", "PluginStorage"]


from ._core import PluginInfo, Plugin, PluginStorage

STORAGE: PluginStorage = PluginStorage()


def initialize(app):
    STORAGE.load_builtins()
    STORAGE.init(app)
