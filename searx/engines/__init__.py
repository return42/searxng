# SPDX-License-Identifier: AGPL-3.0-or-later
"""Python package in which the engine modules for the
:py:obj:`searx.enginelib.engine.EngineModule` instances are implemented.
"""

from __future__ import annotations

from searx.enginelib.engine_map import EngineMap

ENGINE_MAP: EngineMap = EngineMap([])
"""Global instance of :py:obj:`EngineMap`, see :py:obj:`load_engines`."""


def load_engines(engine_list: list[dict]):
    """Instantiates engines (:py:obj:`ENGINE_MAP`) from the given list of
    engine-setups::

        engine_list = settings['engines']
        ENGINE_MAP = load_engines(engine_list)
    """

    global ENGINE_MAP  # pylint: disable=global-statement
    ENGINE_MAP = EngineMap(engine_list)
    return ENGINE_MAP
