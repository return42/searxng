# SPDX-License-Identifier: AGPL-3.0-or-later
"""

ToDo: needs some documentation ..

"""

from __future__ import annotations

__all__ = ["AnswererInfo", "Answerer", "AnswerStorage"]


from ._core import AnswererInfo, Answerer, AnswerStorage

STORAGE = AnswerStorage(load_defaults=True)
