# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=too-many-branches
"""

- ``hostnames.replace``: A **mapping** of regular expressions to hostnames to be
  replaced by other hostnames.

  .. code:: yaml

     hostnames:
       replace:
         '(.*\\.)?youtube\\.com$': 'invidious.example.com'
         '(.*\\.)?youtu\\.be$': 'invidious.example.com'
         ...

- ``hostnames.remove``: A **list** of regular expressions of the hostnames whose
  results should be taken from the results list.

  .. code:: yaml

     hostnames:
       remove:
         - '(.*\\.)?facebook.com$'
         - ...

- ``hostnames.high_priority``: A **list** of regular expressions for hostnames
  whose result should be given higher priority. The results from these hosts are
  arranged higher in the results list.

  .. code:: yaml

     hostnames:
       high_priority:
         - '(.*\\.)?wikipedia.org$'
         - ...

- ``hostnames.lower_priority``: A **list** of regular expressions for hostnames
  whose result should be given lower priority. The results from these hosts are
  arranged lower in the results list.

  .. code:: yaml

     hostnames:
       low_priority:
         - '(.*\\.)?google(\\..*)?$'
         - ...

If the URL matches the pattern of ``high_priority`` AND ``low_priority``, the
higher priority wins over the lower priority.

Alternatively, you can also specify a file name for the **mappings** or
**lists** to load these from an external file:

.. code:: yaml

   hostnames:
     replace: 'rewrite-hosts.yml'
     remove:
       - '(.*\\.)?facebook.com$'
       - ...
     low_priority:
       - '(.*\\.)?google(\\..*)?$'
       - ...
     high_priority:
       - '(.*\\.)?wikipedia.org$'
       - ...

The ``rewrite-hosts.yml`` from the example above must be in the folder in which
the ``settings.yml`` file is already located (``/etc/searxng``). The file then
only contains the lists or the mapping tables without further information on the
namespaces.  In the example above, this would be a mapping table that looks
something like this:

.. code:: yaml

   '(.*\\.)?youtube\\.com$': 'invidious.example.com'
   '(.*\\.)?youtu\\.be$': 'invidious.example.com'

"""

from __future__ import annotations
import typing

import re
from urllib.parse import urlunparse, urlparse

from flask_babel import gettext

from searx import settings
from searx.settings_loader import get_yaml_cfg
from searx.plugins import Plugin, PluginInfo

if typing.TYPE_CHECKING:
    import flask
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.result_types import Result
    from searx.plugins import PluginCfg


REPLACE: dict[re.Pattern, str] = {}
REMOVE: set = set()
HIGH: set = set()
LOW: set = set()


class SXNGPlugin(Plugin):
    """Rewrite hostnames, remove results or prioritize them."""

    id = "hostnames"
    url_fields = ["iframe_src", "audio_src"]

    def __init__(self, plg_cfg: "PluginCfg") -> None:
        super().__init__(plg_cfg)
        self.info = PluginInfo(
            id=self.id,
            name=gettext("Hostnames plugin"),
            description=gettext("Rewrite hostnames, remove results or prioritize them based on the hostname"),
            preference_section="general",
        )

    def on_result(
        self, request: "SXNG_Request", search: "SearchWithPlugins", result: Result
    ) -> bool:  # pylint: disable=unused-argument

        for pattern in REMOVE:

            if result.parsed_url and pattern.search(result.parsed_url.netloc):
                # if the link (parsed_url) of the result match, then remove the
                # result from the result list, in any other case, the result
                # remains in the list / see final "return True" below.
                return False

            for field in self.url_fields:
                url_src = getattr(result, field, None)
                if not url_src:
                    continue

                # if url in a field matches, then just delete the field
                url_src = urlparse(url_src)
                if pattern.search(url_src.netloc):
                    setattr(result, field, None)

        for pattern, replacement in REPLACE.items():

            if result.parsed_url and pattern.search(result.parsed_url.netloc):
                result.parsed_url = result.parsed_url._replace(
                    netloc=pattern.sub(replacement, result.parsed_url.netloc)
                )
                result.url = urlunparse(result.parsed_url)

            for field in self.url_fields:
                url_src = getattr(result, field, None)
                if not url_src:
                    continue

                url_src = urlparse(url_src)
                if pattern.search(url_src.netloc):
                    url_src = url_src._replace(netloc=pattern.sub(replacement, url_src.netloc))
                    setattr(result, field, urlunparse(url_src))

        for pattern in LOW:
            if result.parsed_url and pattern.search(result.parsed_url.netloc):
                result.priority = "low"

        for pattern in HIGH:
            if result.parsed_url and pattern.search(result.parsed_url.netloc):
                result.priority = "high"

        # the result remains in the list
        return True

    def init(self, app: "flask.Flask") -> bool:  # pylint: disable=unused-argument
        global REPLACE, REMOVE, HIGH, LOW

        REPLACE = _load_regular_expressions("replace") or {}  # type: ignore
        REMOVE = _load_regular_expressions("remove") or set()  # type: ignore
        HIGH = _load_regular_expressions("high_priority") or set()  # type: ignore
        LOW = _load_regular_expressions("low_priority") or set()  # type: ignore

        return True

    def _load_regular_expressions(self, settings_key) -> dict[re.Pattern, str] | set | None:
        setting_value = settings.get(self.id, {}).get(settings_key)

        if not setting_value:
            return None

        # load external file with configuration
        if isinstance(setting_value, str):
            setting_value = get_yaml_cfg(setting_value)

        if isinstance(setting_value, list):
            return {re.compile(r) for r in setting_value}

        if isinstance(setting_value, dict):
            return {re.compile(p): r for (p, r) in setting_value.items()}

        return None
