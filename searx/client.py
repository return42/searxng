# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
import abc
import babel
from typing import Literal
from collections import defaultdict

import searx
import searx.locales

from searx.exceptions import SearxParameterException
from searx.extended_types import sxng_request
from searx.preferences import Preferences
from searx.query import RawTextQuery
from searx.search import SearchQuery
from searx.utils import detect_language

#     XXXXXXXXX FIXME .. see searx.webadapter !!!

TIME_RANGE = {"day", "week", "month", "year"}
VALID_LANGUAGE_CODE = re.compile(r'^[a-z]{2,3}(-[a-zA-Z]{2})?$')

class Client(abc.ABC):
    """Base class to implement server site of a client."""

    locale: babel.Locale
    """The locale of the client serves as a fallback value for the UI language
    (:py:obj:`Client.language_tag`) and the region/language of the search query
    (:py:obj:`Client.region_tag`)."""

    prefs: Preferences

    def __init__(self, locale: babel.Locale):
        self.locale = locale
        self.prefs = Preferences()
        self.raw_query = RawTextQuery(self.search_term(), self.prefs.disabled_engines)

    @property
    def language_tag(self) -> str|None:
        if self.locale:
            return searx.locales.language_tag(self.locale)
        return None

    @property
    def region_tag(self) -> str|None:
        if self.locale and self.locale.territory:
            return searx.locales.region_tag(self.locale)
        return None

    @abc.abstractmethod
    def search_term(self) -> str:
        """Search term from user input."""

    @abc.abstractmethod
    def pageno(self) -> int:
        """Page number of the search request."""

    @abc.abstractmethod
    def time_range(self) -> Literal["day", "week", "month", "year"]:
        """Time range filter."""

    @abc.abstractmethod
    def safesearch(self) -> int:
        """Safesearch filter."""

    @abc.abstractmethod
    def ui_locale_tag(self) -> str:
        """Language of the user interface (UI)."""

    @abc.abstractmethod
    def search_locale_tag(self) -> str:
        """SearXNG's locale tag of a search query."""

    @abc.abstractmethod
    def timeout_limit(self) -> str:
        """Maximum timeout for the whole search request."""

    @abc.abstractmethod
    def engine_data(self):
        pass

    def external_bang(self) -> str:
        """External bangs (e.g. ``!!wde`` parsed by :py:obj:`searx.query.ExternalBang`)."""
        return self.raw_query.external_bang

        
    def get_search_query(self):

        # parse query, if tags are set, which change the search engine or
        # search-language
        raw_query = RawTextQuery(
            self.search_term(),
            sxng_request.preferences.disabled_engines,
        )

        # set query
        query = raw_query.getQuery()
        pageno =self.pageno
        
        query_safesearch = parse_safesearch(preferences, form)
        query_time_range = parse_time_range(form)
        query_timeout = parse_timeout(form, raw_text_query)
        external_bang = raw_text_query.external_bang
        redirect_to_first_result = raw_text_query.redirect_to_first_result
        engine_data = parse_engine_data(form)




        return SearchQuery(
            query =  query,
            engineref_list = xxx,
            lang = self.search_locale_tag(),  # this is the search locale (not UI language!)
            safesearch = self.safesearch(),
            pageno = self.pageno(),
            time_range = self.time_range(),
            timeout_limit = self.timeout_limit(),
            external_bang = self.external_bang(),
            engine_data= self.engine_data(),
            redirect_to_first_result= xxx,
        )




class HTTPClient(Client):
    """Implements server site of a HTTP client."""

    # FIXME !!! searx.webapp.get_client_settings should be moved into this class !!!

    @classmethod
    def from_http_request(cls):
        """Build ClientPref object from HTTP request.

        - `Accept-Language used for locale setting
          <https://www.w3.org/International/questions/qa-accept-lang-locales.en>`__

        """
        al_header = sxng_request.headers.get("Accept-Language")
        if not al_header:
            return cls(locale=None)

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

        locale = None
        if pairs:
            pairs.sort(reverse=True, key=lambda x: x[1])
            locale = pairs[0][0]
        return cls(locale=locale)

    def search_term(self) -> str:
        """Search term from user input."""
        return sxng_request.form.get("q", "")

    def pageno(self) -> int:
        """Page number selected in the HTML ``<form>``."""
        n = sxng_request.form.get("pageno", "1")
        if not n.isdigit() or int(n) < 1:
            raise SearxParameterException("pageno", n)
        return int(n)

    def time_range(self) -> Literal["day", "week", "month", "year"]|None:
        """Time range option from the HTML form (``time_range``)."""
        val = sxng_request.form.get("time_range")
        if val is not None and val not in TIME_RANGE:
            raise SearxParameterException("time_range", val)
        return val

    def safesearch(self) -> int:
        """Safesearch option from the HTML form (``safesearch``)."""
        pref = self.prefs.components["safesearch"]
        str_val = sxng_request.form.get("safesearch", None)
        if pref.locked or str_val is None:
            return pref.value
        try:
            pref.validate(str_val)
        except ValueError:
            raise SearxParameterException("safesearch", str_val)
        return pref.str2val(str_val)

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

        for tag in [
                self.prefs.get("ui_locale_tag", ""),
                searx.get_setting("ui.default_locale", ""),
                self.language_tag,
                "en",
        ]:
            if tag:
                break
        return tag

    def search_locale_tag(self) -> str:
        """SearXNG's search language /  locale of a query comes from:

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
                self.sxng_request.form.get("search_locale", ""),
                self.prefs.get("ui_locale_tag", ""),
                searx.get_setting("ui.default_locale", ""),
        ]:
            if tag:
                search_locale = tag
                break

        if not (search_locale in ["", "auto", "all" ] or VALID_LANGUAGE_CODE.match(search_locale)):
            raise SearxParameterException("search_locale", search_locale)

        if search_locale in ["", "auto"]:
            lang = detect_language(self.raw_query, threshold=0.8, only_search_languages=True)
            if lang:
                search_locale = lang

        return search_locale


    def timeout_limit(self) -> float|None:
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
            limit = self.sxng_request.form.get("timeout_limit")
            try:
                limit = float(limit)
            except ValueError as exc:
                raise SearxParameterException('timeout_limit', limit) from exc
        return limit

    def engine_data(self):
        # hack to pass engine_data from one HTTP request (page) to the next HTTP
        # request (page), see:
        # - searx.results.ResultContainer.engine_data
        # - searx/templates/simple/results.html macro engine_data_form

        data = defaultdict(dict)
        for key, val in self.sxng_request.form.items():
            if key.startswith("engine_data"):
                _, engine, key = key.split('-')
                data[engine][key] = val
        return data
