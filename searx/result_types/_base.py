# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=too-few-public-methods, missing-module-docstring

from __future__ import annotations

__all__ = ["Result"]

import re
import urllib.parse
import warnings

import msgspec


class Result(msgspec.Struct, kw_only=True):
    """Abstract base class of all result types.

    - :ref:`engine results`
    - :py:obj:`Answer`
    - :py:obj:`Translations`
    - ...
    """

    results: list
    """Result list of a :origin:`engine <searx/engines>` response or a
    :origin:`answerer <searx/answerers>` to which the answer should be added."""

    engine: str | None = ""
    """Name of the engine name *this* result comes from.  In case of *plugins* a
    prefix ``plugin:`` is set, in case of *answerer* prefix ``answerer: is
    set.``"""

    template: str = "default.html"
    """Name of the template used to render the result"""

    url: str | None = None
    """A link related to the *result*"""

    parsed_url: urllib.parse.ParseResult | None = None
    """:py:obj:`urllib.parse.ParseResult` of :py:obj:`Result.url`."""

    def normalize_result_fields(self):
        """Normalize a result ..

        - if field ``url`` is set and field `parse_url` is unset, init ``parse_url``
          from field ``url``.  This method can be extended in the inheritance.
        """

        if not self.parsed_url and self.url:
            self.parsed_url = urllib.parse.urlparse(self.url)

            # if the result has no scheme, use http as default
            if not self.parsed_url.scheme:
                self.parsed_url = self.parsed_url._replace(scheme="http")
                self.url = self.parsed_url.geturl()

    def __post_init__(self):
        """Add *this* result to the result list."""

        self.results.append(self)

    def __hash__(self) -> int:
        """The hash value is used in :py:obj:`set`, for example, when an object
        is added to the set.  The hash value is also used in other contexts,
        e.g. when checking for equality to identify identical results from
        different sources (engines)."""

        return id(self)

    def __eq__(self, other):
        """py:obj:`Result` objects are equal if the hash values of the two
        objects are equal.  If needed, its recommended to overwrite
        "py:obj:`Result.__hash__`."""

        return hash(self) == hash(other)

    # for legacy code where a result is treated as a Python dict

    def __setitem__(self, field_name, value):

        return setattr(self, field_name, value)

    def __getitem__(self, field_name):

        if field_name not in self.__struct_fields__:
            raise KeyError(f"{field_name}")
        return getattr(self, field_name)

    def __iter__(self):

        return iter(self.__struct_fields__)


class LegacyResult(dict):
    """A wrapper around a legacy result item.  The SearXNG core uses this class
    for untyped dictionaries / to be downward compatible.

    This class is needed until we have implemented a :obj_py:`Result` class for
    each result type and the old usages have fully disappeared from the code
    base.

    .. note::

       There is only one place where this class is used, in the
       `ResultContainer`.

       Do not use this class in your own implementations!

    template:
      Name of the template used to render the result (default:
      :origin:`result_templates/default.html <searx/templates/simple/result_templates/default.html>`.
    """

    UNSET = object()
    WHITESPACE_REGEX = re.compile('( |\t|\n)+', re.M | re.U)

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.__dict__ = self

        # Init fields with defaults / compare with defaults of the fields in class Result
        self.engine = self.get("engine", "")
        self.template = self.get("template", "default.html")
        self.url = self.get("url", None)
        self.parsed_url = self.get("parsed_url", None)

        self.content = self.get("content", "")
        self.title = self.get("title", "")

        # Legacy types that have already been ported to a type ..

        if "answer" in self:
            warnings.warn(
                f"engine {self.engine} is using deprecated `dict` for answers"
                f" / use a class from searx.result_types.answer",
                DeprecationWarning,
            )
            self.template = "answer/legacy.html"

    def __hash__(self) -> int:  # type: ignore

        if "answer" in self:
            return hash(self["answer"])
        return id(self)

    def __eq__(self, other):

        return hash(self) == hash(other)

    def __repr__(self) -> str:

        return f"LegacyResult: {super().__repr__()}"

    def __getattr__(self, name: str, default=UNSET):

        if default == self.UNSET and name not in self:
            raise AttributeError(f"LegacyResult object has no field named: {name}")
        return self[name]

    def __setattr__(self, name: str, val):

        self[name] = val

    def normalize_result_fields(self):

        self.title = self.WHITESPACE_REGEX.sub(" ", self.title)

        if not self.parsed_url and self.url:
            self.parsed_url = urllib.parse.urlparse(self.url)

            # if the result has no scheme, use http as default
            if not self.parsed_url.scheme:
                self.parsed_url = self.parsed_url._replace(scheme="http")
                self.url = self.parsed_url.geturl()

        if self.content:
            self.content = self.WHITESPACE_REGEX.sub(" ", self.content)
            if self.content == self.title:
                # avoid duplicate content between the content and title fields
                self.content = ""