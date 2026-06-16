# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, too-few-public-methods

import typing as t

import re
import urllib.parse

import msgspec
from flask_babel import gettext  # pyright: ignore[reportUnknownVariableType]
from searx import get_setting
from searx.plugins import Plugin, PluginInfo, PluginCfg, StoragePlgCfg
from searx.extended_types import sxng_request

from ._core import log, PluginCfg

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.extended_types import SXNG_Request
    from searx.result_types import Result, LegacyResult  # pyright: ignore[reportPrivateLocalImportUsage]


def filter_url_field(result: "Result|LegacyResult", field_name: str, url_src: str) -> bool | str:
    """Returns bool ``True`` to use URL unchanged (``False`` to ignore URL).
    If URL should be modified, the returned string is the new URL to use."""

    if field_name != "url":
        return True  # use it unchanged

    resolver_url = get_doi_resolver()
    if not resolver_url:
        return True  # use it unchanged

    doi = extract_doi(result.parsed_url)  # pyright: ignore[reportArgumentType]
    if doi and len(doi) < 50:
        for suffix in ("/", ".pdf", ".xml", "/full", "/meta", "/abstract"):
            doi = doi.removesuffix(suffix)
        new_url = resolver_url + doi
        if "doi" not in result:
            result["doi"] = doi
        log.debug("oa_doi_rewrite: [URL field: %s] %s -> %s", field_name, url_src, new_url)
        return new_url  # use new url

    return True  # use it unchanged


class DOICfg(PluginCfg):
    """Setup of the DOI plugin.

    .. code: yaml

       searx.plugins.oa_doi_rewrite.SXNGPlugin:
         active: true
         cfg:          # <-- DOICfg
           resolvers:
             oadoi.org: https://oadoi.org/"
             doi.org: https://doi.org/"
             sci-hub.se: https://sci-hub.se/"
             sci-hub.st: https://sci-hub.st/"
             sci-hub.ru: https://sci-hub.ru/"
    """
    resolvers: dict[str, str] = msgspec.field(default_factory=dict)




@t.final
class SXNGPlugin(Plugin[DOICfg]):
    """Avoid paywalls by redirecting to open-access."""

    id = "oa_doi_rewrite"

    cfg_cls = DOICfg

    def __init__(self, storage_cfg: StoragePlgCfg) -> None:
        super().__init__(storage_cfg)
        self.info = PluginInfo(
            id=self.id,
            name=gettext("Open Access DOI rewrite"),
            description=gettext("Avoid paywalls by redirecting to open-access versions of publications when available"),
            preference_section=None,
        )

    def on_result(
        self,
        request: "SXNG_Request",
        search: "SearchWithPlugins",
        result: "Result",
    ) -> bool:  # pylint: disable=unused-argument
        if result.parsed_url:
            result.filter_urls(filter_url_field)
        return True


regex = re.compile(r"10\.\d{4,9}/[^\s]+")


def extract_doi(url: urllib.parse.ParseResult):
    m = regex.search(url.path)
    if m:
        return m.group(0)
    for _, v in urllib.parse.parse_qsl(url.query):
        m = regex.search(v)
        if m:
            return m.group(0)
    return None


def get_doi_resolver() -> str:
    doi_resolvers = get_setting("doi_resolvers")
    selected_resolver = sxng_request.preferences.get_value("doi_resolver")
    if not selected_resolver or selected_resolver not in doi_resolvers:
        return ""
    return doi_resolvers[selected_resolver]
