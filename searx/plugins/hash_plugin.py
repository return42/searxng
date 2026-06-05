# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plugin converts strings to different hash digests.

The results are displayed in area for the "answers".
"""

import typing as t

import re
import hashlib

from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]

from searx.plugins import Plugin, PluginInfo, PluginCfg, PluginPrefs

from searx.result_types import EngineResults

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request


@t.final
class Info(PluginInfo):
    # pylint: disable=missing-class-docstring

    name = lazy_gettext("Hash plugin")
    preference_section = "query"
    examples = ["sha512 The quick brown fox jumps over the lazy dog"]
    description = lazy_gettext(
        "Converts strings to different hash digests. Available functions: md5, sha1, sha224, sha256, sha384, sha512."
    )


@t.final
class SXNGPlugin(Plugin[Info, PluginCfg, PluginPrefs]):
    # pylint: disable=missing-class-docstring

    id = "hash_plugin"
    info_factory = Info
    keywords = ["md5", "sha1", "sha224", "sha256", "sha384", "sha512"]
    parser_re = re.compile(f"({'|'.join(keywords)}) (.*)", re.I)

    def post_search(self, request: "SXNG_Request", search: "SearchWithPlugins") -> EngineResults:
        """Returns a result list only for the first page."""
        res = EngineResults()

        if search.search_query.pageno > 1:
            return res

        m = self.parser_re.match(search.search_query.query)
        if not m:
            # wrong query
            return res

        function, string = m.groups()
        if not string.strip():
            # end if the string is empty
            return res

        # select hash function
        f = hashlib.new(function.lower())

        # make digest from the given string
        f.update(string.encode("utf-8").strip())

        l10n = lazy_gettext("hash digest")
        res.add(
            res.types.Answer(
                answer=f"{function} {l10n}: {f.hexdigest()}",
            )
        )

        return res
