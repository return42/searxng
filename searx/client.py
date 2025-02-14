# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import babel

import searx.locales
from searx.extended_types import sxng_request


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
