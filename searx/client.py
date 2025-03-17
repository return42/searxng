# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations
from dataclasses import dataclass
import typing

import abc
import base64
import re
import logging
from collections import defaultdict

import babel
import babel.core
from flask_babel import gettext
import msgspec

import searx
import searx.locales
import searx.engines
import searx.webutils

from searx.exceptions import SearxParameterException
from searx.settings_defaults import URLFormattingType, HTTPMethodeType
from searx.extended_types import sxng_request
from searx.query import RawTextQuery
from searx.search import SearchQuery
from searx.plugins.oa_doi_rewrite import get_doi_resolver

from searx.utils import detect_language

from searx.components.filters import SafeSearchType, SAFE_SEARCH_CATALOG, TIME_RANGE_CATALOG, TimeRangeType

if typing.TYPE_CHECKING:
    from searx.preferences import Preferences

log = logging.getLogger(__name__)

VALID_LANGUAGE_CODE = re.compile(r'^[a-z]{2,3}(-[a-zA-Z]{2})?$')
PREF: "Preferences" = sxng_request.preferences


class Client(abc.ABC):
    """Base class to implement server site of a client."""

    locale: babel.Locale
    """The locale of the client serves as a fallback value for the UI language
    (:py:obj:`Client.language_tag`) and the region/language of the search query
    (:py:obj:`Client.region_tag`)."""

    def __init__(self, locale: babel.Locale):
        self.locale = locale
        self._raw_query = None

    @property
    def raw_query(self) -> RawTextQuery:
        if self._raw_query is None:
            self._raw_query = RawTextQuery(self.search_term, PREF.fields.engines.disabled_engines)
        return self._raw_query

    @property
    def language_tag(self) -> str | None:
        if self.locale:
            return searx.locales.language_tag(self.locale)
        return None

    @property
    def region_tag(self) -> str | None:
        if self.locale and self.locale.territory:
            return searx.locales.region_tag(self.locale)
        return None

    @property
    def rtl(self) -> bool:
        return bool(self.ui_locale_tag in searx.locales.LOCALE_NAMES)

    @property
    @abc.abstractmethod
    def search_term(self) -> str:
        """Search term from user input."""

    @property
    @abc.abstractmethod
    def pageno(self) -> int:
        """Page number of the search request."""

    @property
    @abc.abstractmethod
    def time_range(self) -> TimeRangeType:
        """Time range filter."""

    @property
    @abc.abstractmethod
    def safesearch(self) -> SafeSearchType:
        """Safesearch filter."""

    @property
    @abc.abstractmethod
    def ui_locale_tag(self) -> str:
        """Language of the user interface (UI)."""

    @property
    @abc.abstractmethod
    def search_locale_tag(self) -> str:
        """SearXNG's locale tag of a search query."""

    @property
    @abc.abstractmethod
    def timeout_limit(self) -> float | None:
        """Maximum timeout for the whole search request."""

    @property
    @abc.abstractmethod
    def engine_names(self) -> set[str]:
        pass

    @property
    @abc.abstractmethod
    def engine_data(self) -> dict[str, dict[str, str]]:
        pass

    @property
    def external_bang(self) -> str | None:
        """External bangs (e.g. ``!!wde`` parsed by :py:obj:`searx.query.ExternalBang`)."""
        return self.raw_query.external_bang

    def get_search_query(self) -> SearchQuery:

        return SearchQuery(
            query=self.raw_query.getQuery(),
            engine_names=self.engine_names,
            search_locale_tag=self.search_locale_tag,
            safesearch=self.safesearch,
            pageno=self.pageno,
            time_range=self.time_range,
            timeout_limit=self.timeout_limit,
            external_bang=self.external_bang,
            engine_data=self.engine_data,
            redirect_to_first_result=self.raw_query.redirect_to_first_result,
        )


class HTTPClient(Client):
    """Implements server site of a HTTP client."""

    def __init__(self, locale: babel.Locale):
        super().__init__(locale)
        self._settings = None

    @property
    def settings(self):
        if not self._settings:
            self._settings = HTTPClientSettings.get_instance()
        return self._settings

    @classmethod
    def from_http_request(cls):
        """Build HTTPClient object from HTTP request.

        - `Accept-Language used for locale setting
          <https://www.w3.org/International/questions/qa-accept-lang-locales.en>`__

        """

        al_header = sxng_request.headers.get("Accept-Language")
        if not al_header:
            return cls(locale=babel.Locale("en"))

        pairs = []
        for lang_item in al_header.split(","):
            # fmt: off
            lang, qvalue = [_.strip() for _ in (lang_item.split(";") + ["q=1",])[:2]]
            # fmt: on
            try:
                qvalue = float(qvalue.split("=")[-1])
                locale = babel.Locale.parse(lang, sep="-")
            except (ValueError, babel.core.UnknownLocaleError):
                continue
            pairs.append((locale, qvalue))

        locale = "en"
        if pairs:
            pairs.sort(reverse=True, key=lambda x: x[1])
            locale = pairs[0][0]
        return cls(locale=babel.Locale.parse(locale))

    @property
    def search_term(self) -> str:
        """Search term from user input."""
        return sxng_request.form.get("q", "")

    @property
    def pageno(self) -> int:
        """Page number selected in the HTML ``<form>``."""
        n = sxng_request.form.get("pageno", "1")
        if not n.isdigit() or int(n) < 1:
            raise SearxParameterException("pageno", n)
        return int(n)

    @property
    def time_range(self) -> TimeRangeType:
        """Time range option from the HTML form (``time_range``)."""
        # FIXME: implement a ..forms.filters.TimeRange component for the /search
        # form.
        val = sxng_request.form.get("time_range", "")
        if val not in TIME_RANGE_CATALOG:
            raise SearxParameterException("time_range", val)
        return val

    @property
    def safesearch(self) -> SafeSearchType:
        """Safesearch option, first match is used:

        - is set in the HTML form (``safesearch``) otherwise
        - default value is taken from the preferences
        """
        value = PREF.fields.safesearch.value

        # FIXME: implement a ..forms.filters.SafeSearch component for the /search
        # form.
        string = sxng_request.form.get("safesearch", None)

        if string is not None:
            try:
                value = PREF.fields.safesearch.str2val(string)
            except ValueError:
                log.error(f"got invalid safesearch value from HTTP client: '{string}'")

        if value not in SAFE_SEARCH_CATALOG:
            log.error(f"invalid safesearch value: {repr(value)}")
        return value

    @property
    def ui_locale_tag(self) -> str:
        """Language of the user interface (UI).  The preferred translation_ of
        the user interface is determined as follows:

        1. the user has set a locale in the preferences (``ui_locale_tag``), or
        2. the :py:obj:`ui:default_locale <settings ui>` is set, or
        3. the `Accept-Language` header from user's HTTP client, or
        3. there are no preferences, no settings at all: default ``en``.

        Examples of valid values:

        - ``en``, ``fr``, ``de``, ``fil`` .. ``nb-NO``, ``zh-TW``

        Examples for which there are no translations_:

        - ``en-US``, ``fr-fr``, ``de-de``, .. ``nb``, ``zh``

        _translation: https://translate.codeberg.org/projects/searxng/searxng/

        """

        tag = "en"
        for tag in [
            PREF.fields.ui_locale_tag.value,
            searx.get_setting("ui.default_locale", ""),
            self.language_tag,
        ]:
            if tag:
                break
        return tag

    @property
    def search_locale_tag(self) -> str:
        """SearXNG's search language/locale of a query comes from:

        1. the locale is given by the :ref:`search-syntax`
           (e.g. `:zh-TW` parsed by :py:obj:`searx.query.SearchLocale`), if not ..

        2. the user selects a locale from the menu of the query form
           (e.g. ``zh-TW``), if not ..

        3. the user has set a locale in the preferences, if not ..

        4. the :ref:`search:default_lang <settings search>` is used.  If the
           maintainer of the instance has not made any adjustments here, the
           value is ``auto``.

        The selection options for 2. can be restricted by the setting
        :ref:`search:languages <settings search>`.

        If the locale tag from 1. 2. 3. or 4. is:

        ``auto``:
          The search term is examined to determine the preferred search language
          (fastText).  If no preferred language can be determined from the
          search term, the Accept-Language (:py:obj:`Client.language_tag`)

        ``all``:
          No language or locale is specified, it is up to the engines how they
          deal with it, most engines fall back to a default and that is usually
          `en`.
        """

        search_locale = ""
        for tag in [
            self.raw_query.search_locale_tag,
            sxng_request.form.get("search_locale", ""),
            PREF.fields.ui_locale_tag.value,
            # HINT: ui.default_locale is already the default of preference ui_locale_tag
            # searx.get_setting("ui.default_locale", ""),
        ]:
            if tag:
                search_locale = tag
                break

        if not (search_locale in ["", "auto", "all"] or searx.locales.VALID_LANGUAGE_CODE.match(search_locale)):
            raise SearxParameterException("search_locale", search_locale)

        if search_locale in ["", "auto"]:
            lang = detect_language(self.raw_query.getQuery(), threshold=0.8, only_search_languages=True)
            if lang:
                search_locale = lang

        return search_locale

    @property
    def timeout_limit(self) -> float | None:
        """Maximum timeout for the whole search request. The timeout limit comes
        from:

        1. the timeout limit is given by the :ref:`search-syntax` (e.g. ``<3``
           or ``<200`` parsed by :py:obj:`searx.query.Timeout`), if not ..

        2. the ``timeout_limit`` element in the HTML form, a string with a float
           (e.g. "3" or "0.2" seconds).

        If there is no timeout limit, the return value is ``None`` and the
        timeout is determined by the maximum timeout of all engines involved in
        the search.
        """
        limit = self.raw_query.timeout_limit
        if limit is None:
            limit = sxng_request.form.get("timeout_limit")
            if limit is not None:
                try:
                    limit = float(limit)
                except ValueError as exc:
                    raise SearxParameterException('timeout_limit', limit) from exc
        return limit

    @property
    def engine_names(self) -> set[str]:

        # small helper function ..

        def _engines_in_categories(c_list: list[str]) -> set[str]:
            e = set()
            for c in c_list:
                for eng in searx.engines.categories.get(c, []):
                    if eng.name not in PREF.fields.engines.disabled_engines:
                        e.add(eng.name)
            return e

        # get engine names from categories, !bang & form data

        categs: MultipleChoice = PREF["categories"]  # type: ignore

        if categs.locked:
            return _engines_in_categories(categs.value)

        if self.raw_query.engine_names:
            # use engines selected in the search term by !bang search syntax
            # (!engine and !category)
            return self.raw_query.engine_names

        # remind: we merged GET, POST vars into request.form (see
        # SXNG_Request.form) and here we use `engine` and `categories` from
        # the search-API: https://docs.searxng.org/dev/search_api.html

        eng_names: set[str] = set()
        for name in sxng_request.form.get("engines", "").split(","):
            name = name.strip()
            if name in searx.engines.engines and name not in PREF.fields.engines.disabled_engines:
                eng_names.add(name)

        category_names = [c.strip() for c in sxng_request.form.get("categories", "").split(",")]
        return eng_names | _engines_in_categories(category_names)

    @property
    def engine_data(self) -> dict[str, dict[str, str]]:
        # hack to pass engine_data from one HTTP request (page) to the next HTTP
        # request (page), see:
        # - searx.results.ResultContainer.engine_data
        # - searx/templates/simple/results.html macro engine_data_form

        data = defaultdict(dict)
        for key, val in sxng_request.form.items():
            if key.startswith("engine_data"):
                _, engine, key = key.split('-')
                data[engine][key] = val
        return data


@dataclass
class HTTPClientSettings:
    """Container with informations and settings that are transferred to the
    client.  Those informations are required by the client but also by the
    template framework.

    Examples of this are settings for auto-completion or whether the search
    should be executed as soon as a category is clicked on.  However,
    translations (l10n/i18n) and more are also transferred from the client to
    the server.
    """

    # server settings passed to client
    autocomplete_min: int

    # preferences passed to the client
    autocomplete: bool
    hotkeys: str
    infinite_scroll: bool
    method: HTTPMethodeType
    search_on_category_select: bool
    url_formatting: URLFormattingType

    # other settings passed to client
    doi_resolver: str
    theme_static_path: str
    translations: dict[str, str]

    def as_base64(self) -> str:
        """Turns the instance in a base64 str, which can be passed to the client
        in a HTML template.
        """
        msg = msgspec.json.encode(self)
        return str(base64.b64decode(msg))

    @classmethod
    def get_translations(cls):
        return {
            # when there is autocompletion
            "no_item_found": gettext("No item found"),
            # /preferences: the source of the engine description (wikipedata, wikidata, website)
            "Source": gettext("Source"),
            # infinite scroll
            "error_loading_next_page": gettext("Error loading the next page"),
        }

    @classmethod
    def get_instance(cls):

        theme = "simple"
        theme_static_path = searx.webutils.custom_url_for("static", filename=f"themes/{theme}")

        return cls(
            autocomplete_min=searx.get_setting("search.autocomplete_min"),
            autocomplete=PREF.fields.autocomplete.value,
            hotkeys=PREF.fields.hotkeys.value,
            infinite_scroll=PREF.fields.infinite_scroll.value,
            method=PREF.fields.method.value,
            search_on_category_select=PREF.fields.search_on_category_select.value,
            url_formatting=PREF.fields.url_formatting.value,
            doi_resolver=get_doi_resolver(),
            theme_static_path=theme_static_path,
            translations=cls.get_translations(),
        )
