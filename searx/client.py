# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import babel

import searx.locales
from searx.extended_types import sxng_request
from searx.search import SearchQuery
from searx.query import RawTextQuery
from searx.exceptions import SearxParameterException

#     XXXXXXXXX FIXME .. see searx.webadapter !!!


class HTTPClient:
    """Container to assemble client prefferences and settings."""

    # FIXME !!! searx.webapp.get_client_settings should be moved into this class !!!

    locale: babel.Locale | None
    """Locale preferred by the client."""

    def __init__(self, locale: babel.Locale | None = None):
        self.locale = locale

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
        for lang_item in al_header.split(','):
            # fmt: off
            lang, qvalue = [_.strip() for _ in (lang_item.split(';') + ['q=1',])[:2]]
            # fmt: on
            try:
                qvalue = float(qvalue.split('=')[-1])
                locale = babel.Locale.parse(lang, sep='-')
            except (ValueError, babel.core.UnknownLocaleError):
                continue
            pairs.append((locale, qvalue))

        locale = None
        if pairs:
            pairs.sort(reverse=True, key=lambda x: x[1])
            locale = pairs[0][0]
        return cls(locale=locale)

    @property
    def pageno(self):
        """Page number selected in the HTML ``<form>``."""

        n = sxng_request.form.get("pageno", "1")
        if not n.isdigit() or int(n) < 1:
            raise SearxParameterException('pageno', n)
        return int(n)

    @property
    def safesearch(self):
        """Safesearch option selected in the HTML ``<form>``."""

        pref = sxng_request.preferences.components["safesearch"]
        str_val = sxng_request.form.get("safesearch", None)
        if pref.locked or str_val is None:
            return pref.value
        try:
            pref.validate(str_val)
        except ValueError:
            raise SearxParameterException('safesearch', str_val)
        return pref.str2val(str_val)




    


    
    def get_search_query(self):

        # parse query, if tags are set, which change the search engine or
        # search-language
        raw_query = RawTextQuery(
            sxng_request.form["q"],
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
            query =  xxxx,
            engineref_list = xxx,
            lang = xxx,
            safesearch = xxx,
            pageno = xxx,
            time_range = xxx,
            timeout_limit = xxx,
            external_bang = xxx,
            engine_data= xxx,
            redirect_to_first_result= xxx,
        )
