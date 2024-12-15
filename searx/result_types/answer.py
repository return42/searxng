# SPDX-License-Identifier: AGPL-3.0-or-later
"""Typification of the *answer* results."""
# pylint: disable=too-few-public-methods

from __future__ import annotations

__all__ = ["Answer", "Translations"]

from ._base import Result

import msgspec


class BaseAnswer(Result, kw_only=True):
    """Abstract base class of all answer types."""


class Answer(BaseAnswer, kw_only=True):
    """Simple answer type where the *answer* is a simple string with an optional
    ``url`` field to link a resource (article, map, ..) related to the answer.
    """

    template: str = "answer/legacy.html"

    answer: str
    """Text of the answer."""

    url: str | None = None
    """A link related to the *answer*"""

    def __hash__(self):
        """The hash value of field *answer* is the hash value of the
        :py:obj:`Answer` object.  :py:obj:`Answer <Result.__eq__>` objects are
        equal, when the hash values of both objects are equal."""
        return hash(self.answer)


class Translations(BaseAnswer, kw_only=True):
    """Answer type with a list of translations.

    The items in the list are of type :py:obj:`Translations.Item`:

    .. code:: python

       def response(resp):
           results = []
           ...
           foo_1 = Translations.Item(
               text="foobar",
               synonyms=["bar", "foo"],
               examples=["foo and bar are placeholders"],
           )
           foo_url="https://www.deepl.com/de/translator#en/de/foo"
           ...
           Translations(results=results, translations=[foo], url=foo_url)
    """

    template: str = "answer/translations.html"
    """The template in :origin:`answer/translations.html <searx/templates/simple/answer/translations.html>`"""

    translations: list[Translations.Item]

    class Item(msgspec.Struct, kw_only=True):
        """A single element of the translations / a translation.  A translation
        consists of at least a mandatory ``text`` property (the translation) ,
        optional properties such as *definitions*, *synonyms* and *examples* are
        possible."""

        text: str
        """Translated text."""

        transliteration: str = ""
        """Transliteration_ of the requested translation.

        .. _Transliteration: https://en.wikipedia.org/wiki/Transliteration
        """

        definitions: list[str] = []
        """List of definitions for the requested translation."""

        synonyms: list[str] = []
        """List of synonyms for the requested translation."""

        examples: list[str] = []
        """List of examples for the requested translation."""
