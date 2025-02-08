# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring
from __future__ import annotations

import babel
import babel.core


class SearchQuery:
    """container for all the search parameters (query, language, etc...)"""

    def __init__(
        self,
        query: str,
        engine_names: set[str],
        search_locale_tag: str = "all",
        safesearch: int = 0,
        pageno: int = 1,
        time_range: str | None = None,
        timeout_limit: float | None = None,
        external_bang: str | None = None,
        engine_data: dict[str, dict[str, str]] | None = None,
        redirect_to_first_result: bool | None = None,
    ):  # pylint:disable=too-many-arguments
        self.query = query
        self.engine_names: set[str] = engine_names
        self.search_locale_tag = search_locale_tag
        self.safesearch = safesearch
        self.pageno = pageno
        self.time_range = time_range
        self.timeout_limit = timeout_limit
        self.external_bang = external_bang
        self.engine_data: dict[str, dict[str, str]] = engine_data or {}
        self.redirect_to_first_result = redirect_to_first_result

        self.locale = None
        if self.search_locale_tag:
            try:
                self.locale = babel.Locale.parse(self.search_locale_tag, sep='-')
            except babel.core.UnknownLocaleError:
                pass

    def __repr__(self):
        return "SearchQuery({!r}, {!r}, {!r}, {!r}, {!r}, {!r}, {!r}, {!r}, {!r})".format(
            self.query,
            self.engine_names,
            self.search_locale_tag,
            self.safesearch,
            self.pageno,
            self.time_range,
            self.timeout_limit,
            self.external_bang,
            self.redirect_to_first_result,
        )

    def __eq__(self, other):
        return (
            self.query == other.query
            and self.engine_names == other.engine_names
            and self.search_locale_tag == other.search_locale_tag
            and self.safesearch == other.safesearch
            and self.pageno == other.pageno
            and self.time_range == other.time_range
            and self.timeout_limit == other.timeout_limit
            and self.external_bang == other.external_bang
            and self.redirect_to_first_result == other.redirect_to_first_result
        )

    def __hash__(self):
        return hash(
            (
                self.query,
                self.search_locale_tag,
                self.safesearch,
                self.pageno,
                self.time_range,
                self.timeout_limit,
                self.external_bang,
                self.redirect_to_first_result,
            )
        )

    def __copy__(self):
        return SearchQuery(
            self.query,
            self.engine_names,
            self.search_locale_tag,
            self.safesearch,
            self.pageno,
            self.time_range,
            self.timeout_limit,
            self.external_bang,
            self.engine_data,
            self.redirect_to_first_result,
        )
