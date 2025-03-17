# SPDX-License-Identifier: AGPL-3.0-or-later
"""Components used for search filters."""
from __future__ import annotations

__all__ = [
    "CategoriesAsTabs",
    "SAFE_SEARCH_CATALOG",
    "SafeSearch",
    "SafeSearchType",
    "SearchLocale",
    "TIME_RANGE_CATALOG",
    "TimeRange",
    "TimeRangeType",
]

import typing
from flask_babel import lazy_gettext
from flask_babel.speaklater import LazyString

from searx import get_setting
from searx.sxng_locales import sxng_locales
from searx.extended_types import sxng_request
from searx.settings_defaults import SafeSearchType, SAFE_SEARCH_CATALOG
from .form import SingleChoice, MultipleChoice

TimeRangeType = typing.Literal["day", "week", "month", "year", ""]
TIME_RANGE_CATALOG: tuple[TimeRangeType, ...] = typing.get_args(TimeRangeType)


class TimeRange(SingleChoice):

    value: TimeRangeType
    str2obj: dict[str, TimeRangeTypeType]  # type: ignore

    def __init__(self, name: str, default: str, legend: LazyString | str = "", description: LazyString | str = ""):

        if legend and not description:
            description = legend
            legend = ""
        if not legend and not description:
            description = lazy_gettext("Time range")

        super().__init__(
            name=name,
            default=default,
            catalog={str(i): i for i in TIME_RANGE_CATALOG},
            legend=legend,
            description=description,
            catalog_descr={
                "": lazy_gettext("Anytime"),
                "day": lazy_gettext("Last day"),
                "week": lazy_gettext("Last week"),
                "month": lazy_gettext("Last month"),
                "year": lazy_gettext("Last year"),
            },
        )


class SafeSearch(SingleChoice):

    value: SafeSearchType
    str2obj: dict[str, SafeSearchType]  # type: ignore

    def __init__(self, name: str, default: str):
        super().__init__(
            name=name,
            default=default,
            catalog={str(i): i for i in SAFE_SEARCH_CATALOG},
            legend=lazy_gettext("SafeSearch"),
            description=lazy_gettext("Filter content"),
            catalog_descr={
                "0": lazy_gettext("None"),
                "1": lazy_gettext("Moderate"),
                "2": lazy_gettext("Strict"),
            },
        )

    def str2val(self, string: str | list[str]) -> SafeSearchType:
        # typecast
        val: SafeSearchType = super().str2val(string)  # type: ignore
        return val


class CategoriesAsTabs(MultipleChoice):

    str2obj: set[str]  # type: ignore

    def __init__(
        self,
        name: str,
        default: list[str],
        catalog: set[str],
    ):
        super().__init__(name=name, default=default, catalog=catalog)

    def init(self):
        """In the catalog remove those categories where no engine is in
        (categories without engines should not be available for selection).
        """
        eng_categs = sxng_request.preferences.fields.engines.categories.keys()
        for categ in self.str2obj:
            if categ not in eng_categs:
                self.str2obj.remove(categ)

        # just to verify the defaults are any longer in catalog
        for val in self.default:
            self.str2val(val)


class SearchLocale(SingleChoice):
    """Catalog for the search language, built from :py:obj:`searx.sxng_locales`
    including special entries like ``[all]`` and *auto-detect*.
    """

    value: str

    def __init__(
        self,
        name: str,
        description: LazyString | str = "",
        legend: LazyString | str = "",
        auto_locale: str = "auto",
        ui_class: str = "",
    ):

        special_locales: tuple[tuple[str, str, str, str, str], ...] = (
            ("all", lazy_gettext("Default language") + " [all]", "", "", ""),
            ("auto", lazy_gettext("Auto-detect") + f" [{auto_locale}]", "", "", ""),
        )
        catalog = set()
        catalog_descr = {}
        allowed_tags = get_setting("search.languages")  # hint: default is SXNG_LOCALE_TAGS
        for sxng_tag, lang_name, country_name, _, flag in special_locales + sxng_locales:
            if sxng_tag in allowed_tags:
                catalog.add(sxng_tag)
                catalog_descr[sxng_tag] = " ".join(filter(None, [lang_name, country_name, flag]))

        super().__init__(
            name=name,
            default="auto",
            catalog=catalog,
            description=description,
            legend=legend,
            catalog_descr=catalog_descr,
            ui_class=ui_class,
        )
