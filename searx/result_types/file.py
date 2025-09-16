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
