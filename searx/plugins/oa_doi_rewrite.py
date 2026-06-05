# SPDX-License-Identifier: AGPL-3.0-or-later
"""Avoid paywalls by redirecting a DOI_ to open-access versions of publications
when available.

.. _DOI: https://www.doi.org/the-identifier/what-is-a-doi/
"""
# pylint: disable=missing-class-docstring

import typing as t
import re
import urllib.parse

import msgspec
from flask_babel import lazy_gettext  # type: ignore[reportMissingTypeStubs]
from searx.result_types import Result, Paper
from searx.plugins import Plugin, PluginCfg, PluginInfo, PluginPref


if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.result_types import Result, LegacyResult  # type: ignore[reportPrivateLocalImportUsage]


@t.final
class Cfg(PluginCfg):
    """Setup of the DOI plugin.

    .. code: yaml

       searx.plugins.oa_doi_rewrite.SXNGPlugin:
         active: true
         cfg:          # <-- Cfg
           resolvers:
             oadoi.org: https://oadoi.org"
             doi.org: https://doi.org"
             sci-hub.ru: https://sci-hub.ru"
    """

    resolvers: dict[str, str] = msgspec.field(default_factory=dict)


@t.final
class Info(PluginInfo):
    name = lazy_gettext("Open Access DOI rewrite")
    preference_section = "general"
    description = lazy_gettext("Avoid paywalls by redirecting to open-access versions of publications when available")


class Resolver(PluginPref[str | None]):

    def __init__(self, plg: "SXNGPlugin"):
        super().__init__(
            name="doi_resolver",
            plg=plg,
            default=None,
            catalog={"": None} | plg.cfg.resolvers,
            l10n_descr=lazy_gettext("Open Access DOI resolver"),
        )

        def upd(msg: PluginPref.msg.updated[str]) -> None:
            # If no resolver (None) has been selected, the plugin should be inactive
            plg.active = bool(msg.field.val)

        self.listen(PluginPref.msg.updated, upd)


class DOIPrefs(t.TypedDict):
    doi_resolver: Resolver


@t.final
class SXNGPlugin(Plugin[Info, Cfg]):

    id = "oa_doi_rewrite"
    cfg_factory = Cfg
    info_factory = Info
    prefs: DOIPrefs

    def init(self):
        self.prefs = {"doi_resolver": Resolver(self)}

    def on_result(
        self,
        request: "SXNG_Request",
        search: "SearchWithPlugins",
        result: "Result",
    ) -> bool:  # pylint: disable=unused-argument

        doi_host = self.prefs["doi_resolver"].val
        if doi_host is None:
            return True
        doi_host = doi_host.rstrip("/")

        if isinstance(result, Paper) and result.doi and not result.doi_url:
            if doi := extract_doi(result.doi):
                result.doi_url = f"{doi_host}/{doi}"
                self.log.debug("oa_doi_rewrite: [field: doi_url] '' -> %s", result.doi_url)

        if result.parsed_url:
            if doi := extract_doi(result.parsed_url):
                new_url = f"{doi_host}/{doi}"
                self.log.debug("oa_doi_rewrite: [field: url] %s -> %s", result.url, new_url)
                result.url = new_url
                result.parsed_url = urllib.parse.urlparse(result.url)

        return True


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s]+")


def extract_doi(obj: urllib.parse.ParseResult | str) -> str | None:
    doi: str | None = None
    if isinstance(obj, urllib.parse.ParseResult):
        if match := DOI_PATTERN.search(obj.path):
            doi = match.group(0)
        else:
            for _, v in urllib.parse.parse_qsl(obj.query):
                if match := DOI_PATTERN.search(v):
                    doi = match.group(0)
                    break

    elif isinstance(obj, str):
        if match := DOI_PATTERN.search(obj):
            doi = match.group(0)

    if doi and len(doi) < 50:
        for suffix in ("/", ".pdf", ".xml", "/full", "/meta", "/abstract"):
            doi = doi.removesuffix(suffix)

    return doi
