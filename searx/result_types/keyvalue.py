# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Typification of the *keyvalue* results.  Results of this type are rendered in
the :origin:`keyvalue.html <searx/templates/simple/result_templates/keyvalue.html>`
template.

----

.. autoclass:: KeyValue
   :members:
   :show-inheritance:

"""
# pylint: disable=too-few-public-methods

from __future__ import annotations
import typing

__all__ = ["KeyValue"]

from ._base import MainResult


class KeyValue(MainResult, kw_only=True):
    """Simple table view which maps *key* names (first col) to *values*
    (second col)."""

    template: str = "keyvalue.html"

    kvmap: dict[str,typing.Any]
    """Dictionary with keys and values."""

    def __hash__(self) -> int:
        """The KeyValues objects are checked for object identity, even if all
        fields of two results have the same values, they are different from each
        other.
        """
        return id(self)
