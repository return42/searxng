# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

from __future__ import annotations

import types
import pathlib
from searx.utils import load_module
from searx.result_types.answer import BaseAnswer

_default = pathlib.Path(__file__).parent

class AnswerStorage(dict):
    """A storage for managing the *answerers* of SearXNG.  With the
    :py:obj:`AnswerStorage.ask`” method, a caller can ask questions to all
    *answerers* and receives a list of the results."""

    modules: set[types.ModuleType]

    def __init__(self, load_defaults: bool=False):

        super().__init__()
        self.modules = set()
        if load_defaults:
            self._load_defaults()

    def _load_defaults(self):

        for pkg_dir in _default.iterdir():
            if pkg_dir.name.startswith("_") or not pkg_dir.is_dir() or not (pkg_dir/ "answerer.py").exists():
                continue
            self.load_pkg(pkg_dir)

    def load_pkg(self, pkg_dir: pathlib.Path):
        """load ``answerer.py`` module from a python package directory."""

        # The intention of this rewrite is to be able to load answerers from
        # other Python packages later on.  However, there is currently no
        # configuration for this.  With python's entry points:
        # - https://amir.rachum.com/python-entry-points/
        # this can (by example) be done without the need of a configuration on
        # SearXNG's site.

        mod = load_module("answerer.py", str(pkg_dir))
        if not hasattr(mod, "keywords") or not isinstance(mod.keywords, tuple) or not mod.keywords:
            raise SystemExit(2)

        self.modules.add(mod)
        for kw in mod.keywords:
            self[kw] = self.get(kw, [])
            self[kw].append(mod)

    def ask(self, query: str) -> list[BaseAnswer]:
        """An answerer is identified via keywords, if there is a keyword at the
        first position in the ``query`` for which there is one or more
        answerers, then these are called, whereby the entire ``query`` is passed
        as argument to the answerer function."""

        results = []
        keyword = None
        for keyword in query.split():
            if keyword:
                break

        if not keyword or keyword not in self:
            return results

        for mod in self[keyword]:
            for answer in mod.answer(query):
                # In case of *answers* prefix ``answerer:`` is set, see searx.result_types.Result
                answer.engine = f"answerer: {keyword}"
                results.extend(answer)

        return results

    def info(self) -> list[dict[str, list[str]]]:
        ret_val = []
        for mod in self.modules:
            ret_val.append(
                {
                    "info": mod.self_info,
                    "keywords": mod.keeyword,
                }
            )
        return ret_val

STORAGE = AnswerStorage(load_defaults=True)
