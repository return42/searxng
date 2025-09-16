# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Typification of the *file* results.  Results of this type are rendered in
the :origin:`keyvalue.html <searx/templates/simple/result_templates/file.html>`
template.

----

.. autoclass:: File
   :members:
   :show-inheritance:

"""
# pylint: disable=too-few-public-methods


__all__ = ["File"]

import typing

from ._base import MainResult


class File(MainResult, kw_only=True):
    """Class for results of type *file*"""

    template: str = "file.html"

    filename: str = ""
    """Name of the file."""

    size: str = ""
    """Size of bytes in human readable notation (``MB`` for 1024 * 1024 Bytes
    file size.)"""

    time: str = ""
    """Indication of a time, such as the date of the last modification or the
    date of creation. This is a simple string, the *date* of which can be freely
    chosen according to the context."""

    mtype: str = ""
    """Mimetype type of the file.  For the Mimetypes ``audio`` and ``video``, a
    value can be specified in the :py:obj:`File.embedded` field to embed the
    media type directly in the result."""

    subtype: str = ""
    """Mimetype / subtype of the file."""

    abstract: str = ""
    """Abstract of the file."""

    author: str = ""
    """Author of the file."""

    embedded: str = ""
    """URL of an embedded media type (audio or video) / is collapsible."""
