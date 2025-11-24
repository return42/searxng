# SPDX-License-Identifier: AGPL-3.0-or-later
"""THIS IS A POC!!   [POC:SideCar]

SideCar's tools & services

In this POC, this Python package is provided under the name::

    searx.sidecar_pkg

In a final revised version, this package will be made available for installation
via https://pypi.org/ (?)

"""
# pylint: disable=too-few-public-methods,disable=invalid-name

import typing as t

from .startpage import Startpage
from .google import Google
from .qwant import Qwant
from .loc import Loc
from .ddg import DuckDuckGo
from .mojeek import Mojeek

if t.TYPE_CHECKING:
    from .web_session import WebContainer

MAP_CONTAINER_TYPES: "dict[str, type[WebContainer]]" = {
    Google.name: Google,
    Startpage.name: Startpage,
    Qwant.name: Qwant,
    Loc.name: Loc,
    DuckDuckGo.name: DuckDuckGo,
    Mojeek.name: Mojeek,
}
