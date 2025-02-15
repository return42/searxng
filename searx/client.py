# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import re
import abc
import babel
from typing import Literal

import searx.locales
from searx.extended_types import sxng_request
from searx.search import SearchQuery
from searx.query import RawTextQuery
from searx.exceptions import SearxParameterException
from searx.preferences import Preferences

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
    def language_tag(self) -> str:
        if self.locale:
            return searx.locales.language_tag(self.locale)
        return "en"

    @property
    def region_tag(self) -> str:
        if self.locale and self.locale.territory:
            return searx.locales.region_tag(self.locale)
        return "en-US"

    @abc.abstractmethod
    def search_term(self) -> str:
        """Search term from user input."""

    @abc.abstractmethod
    def pageno(self) -> int:
        """Page number from user input."""

    @abc.abstractmethod
    def time_range(self) -> Literal["day", "week", "month", "year"]:
        """Time range selected by the user."""


    def safesearch(self) -> int:
        """Safesearch option selected by the user (default is taken from
        preferences)."""
        self.prefs.components["safesearch"].value

    def language(self) -> str:
        """SearXNG's locale of a query comes from (*highest wins*):

        1. The user select a locale in the preferences.
        2. The language is given by the :ref:`search-syntax` (e.g. `:zh-TW`)
        5. Autodetection plugin is activated in the preferences and the locale
           (only the language code / none region code) comes from the fastText's
           language detection.
        """
        
        # FIXME: .. see doc string .. in case of "auto" use detect_language !!
        
        
        pref = self.prefs.components["language"]
        if pref.locked or not len(self.raw_query.languages):
            return pref.value
        lang = self.raw_query.languages[-1]
        if not VALID_LANGUAGE_CODE.match(lang) and lang != "auto":
            raise SearxParameterException("language", lang)
        return lang











        
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
            lang = xxx,  # FIXME: this is the query language (not the UI language!)
            safesearch = self.safesearch(),
            pageno = self.pageno(),
            time_range = self.time_range(),
            timeout_limit = xxx,
            external_bang = xxx,
            engine_data= xxx,
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

    def language(self) -> str:
        """SearXNG's locale of a query comes from (*highest wins*):

        1. The `Accept-Language` header from user's HTTP client.
        2. The user select a locale in the preferences.
        3. The user select a locale from the menu in the query form (e.g. `zh-TW`)
        4. The language is given by the :ref:`search-syntax` (e.g. `:zh-TW`)
        5. Autodetection plugin is activated in the preferences and the locale
           (only the language code / none region code) comes from the fastText's
           language detection.
        """

        # FIXME: .. see doc string .. in case of "auto" use detect_language !!

        pref = self.prefs.components["language"]
        if pref.locked:
            return pref.value
        lang = sxng_request.form.get("language", None)
        if len(self.raw_query.languages):
            lang = self.raw_query.languages[-1]
        if not VALID_LANGUAGE_CODE.match(lang) and lang != "auto":
            raise SearxParameterException("language", lang)
        return lang



