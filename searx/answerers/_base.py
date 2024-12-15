# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=too-few-public-methods

from __future__ import annotations

import abc
from dataclasses import dataclass
import pathlib

from searx.utils import load_module
from searx.result_types.answer import BaseAnswer


_default = pathlib.Path(__file__).parent


@dataclass
class AnswererInfo:
    """Object that holds informations about an answerer, these infos are shown
    to the user in the Preferences menu.

    To be able to translate the information into other languages, the text must
    be written in English and translated with :py:obj:`flask_babel.gettext`.
    """

    name: str
    """Name of the *answerer*."""

    description: str
    """Short description of the *answerer*."""

    examples: list[str]
    """Short examples of the usage / of query terms."""

    keywords: list[str]
    """See :py:obj:`Answerer.keywords`"""


class Answerer(abc.ABC):
    """Base class of answerers"""

    keywords: list[str]
    """Key words to which the answerer has *answers*."""

    @abc.abstractmethod
    def answer(self, query: str) -> list[BaseAnswer]:
        """Function that returns a list of answers to the question/query."""

    @abc.abstractmethod
    def info(self) -> AnswererInfo:
        """Returns a dictioniary with infos shown to the user in the preference
        menu."""


class ModuleAnswerer(Answerer):

    def __init__(self, mod):

        for name in ["keywords", "self_info", "answer"]:
            if not getattr(mod, name, None):
                raise SystemExit(2)
        if not isinstance(mod.keywords, tuple):
            raise SystemExit(2)

        self.module = mod
        self.keywords = mod.keywords  # type: ignore

    def answer(self, query: str) -> list[BaseAnswer]:
        return self.module.answer(query)

    def info(self) -> AnswererInfo:
        kwargs = self.module.self_info()
        kwargs["keywords"] = self.keywords
        return AnswererInfo(**kwargs)


class AnswerStorage(dict):
    """A storage for managing the *answerers* of SearXNG.  With the
    :py:obj:`AnswerStorage.ask`” method, a caller can ask questions to all
    *answerers* and receives a list of the results."""

    answerer_list: set[Answerer]

    def __init__(self, load_defaults: bool = False):

        super().__init__()
        self.answerer_list = set()
        if load_defaults:
            self._load_defaults()

    def _load_defaults(self):
        """load ``answerer.py`` module from a python package directory."""

        # The intention of this rewrite is to be able to load answerers from
        # other Python packages later on.  However, there is currently no
        # configuration for this.  With python's entry points:
        # - https://amir.rachum.com/python-entry-points/
        # this can (by example) be done without the need of a configuration on
        # SearXNG's site.

        for pkg_dir in _default.iterdir():
            if pkg_dir.name.startswith("_") or not pkg_dir.is_dir() or not (pkg_dir / "answerer.py").exists():
                continue
            mod = load_module("answerer.py", str(pkg_dir))
            self.add(ModuleAnswerer(mod))

    def add(self, answerer: Answerer):

        self.answerer_list.add(answerer)
        for kw in answerer.keywords:
            self[kw] = self.get(kw, [])
            self[kw].append(answerer)

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

        for answerer in self[keyword]:
            for answer in answerer.answer(query):
                # In case of *answers* prefix ``answerer:`` is set, see searx.result_types.Result
                answer.engine = f"answerer: {keyword}"
                results.append(answer)

        return results

    @property
    def info(self) -> list[AnswererInfo]:
        return [a.info() for a in self.answerer_list]
