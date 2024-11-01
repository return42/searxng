# SPDX-License-Identifier: AGPL-3.0-or-later
"""Implementations of the framework for the SearXNG engines.

.. hint::

   The long term goal is to modularize all implementations of the engine
   framework here in this Python package.  ToDo:

   - move implementations of the :ref:`searx.engines loader` to a new module in
     the :py:obj:`searx.enginelib` namespace.

"""
from __future__ import annotations

__all__ = ["Engine", "EngineMap"]

from .engine import Engine
from .engine_map import EngineMap
