# SPDX-License-Identifier: AGPL-3.0-or-later
"""Manage engine instances in a map that maps from instance's name to Engine instance."""

from __future__ import annotations

__all__ = ["EngineMap"]

import collections
import logging
import msgspec

from searx import logger as log, get_setting
from .engine import Engine

log: logging.Logger = log.getChild("engine_map")


class EngineMap(collections.UserDict[str, Engine]):
    """A python dictionary to map :class:`Engine` by engine's ``name``."""

    __slots__ = (
        "categories",
        "shortcuts",
        "categories_as_tabs",
    )

    DEFAULT_CATEGORY = 'other'

    def __init__(self, engine_list: list[dict], only_actvie: bool = True):
        """Initilaize by ``engine_list`` a python list of ``engine_settings``
        (a python dict with the settings of the instance)."""

        super().__init__()
        self.categories: dict[str, list] = {'general': []}
        self.shortcuts: dict[str, str] = {}
        self.categories_as_tabs: list = get_setting("categories_as_tabs", [])  # type: ignore

        for engine_settings in engine_list:

            try:
                eng = Engine.from_engine_settings(engine_settings)

            except BaseException as exc:
                log.exception(exc)
                log.error(
                    "EngineMap: '%s' (%s) due to above exception engine_settings are ignored/skipped ..",
                    engine_settings.get("name", "<missing 'name'>"),
                    engine_settings.get("engine", "<missing 'engine'>"),
                )
                continue

            # if none of the engine.categories is in the categories_as_tabs
            # config, then add the engine to the DEFAULT_CATEG
            if not any(cat in self.categories_as_tabs for cat in eng.categories):
                eng.categories.append(self.DEFAULT_CATEGORY)

            # ignore inactive engines
            if only_actvie and not eng.is_active:
                log.debug("EngineMap: '%s' (%s) is not active / skipped ..", eng.name, eng.engine)
                continue

            # register engine
            self.register_engine(eng)

    def register_engine(self, eng: Engine):

        # exists a engine with identical name?
        if self.get(eng.name, msgspec.UNSET) != msgspec.UNSET:
            raise ValueError(f"Engine config error: ambiguous name: {eng.name}")
        self[eng.name] = eng

        # exists an engine with identical shortcut?
        if eng.shortcut in self.shortcuts:
            raise ValueError(f"Engine {eng.name} config error, ambiguous shortcut: {eng.shortcut}")
        self.shortcuts[eng.shortcut] = eng.name

        for categ_name in eng.categories:
            self.categories.setdefault(categ_name, []).append(eng)
