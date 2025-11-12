# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!  [POC:SideCar]"""
# pylint: disable=invalid-name, too-few-public-methods

import typing as t

HTTP_COOKIE_Type: t.TypeAlias = dict[str, str]
HTTP_HEADER_Type: t.TypeAlias = dict[str, str]

SessionType: t.TypeAlias = t.Literal[
    "google.com",
    "startpage.com",
    "qwant.com",
]
SESSION_TYPES: t.Final[tuple[SessionType]] = t.get_args(SessionType)
