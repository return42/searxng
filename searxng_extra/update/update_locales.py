#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Update locale names in :origin:`searx/data/locales.json` used by
:ref:`searx.locales`

- :py:obj:`searx.locales.RTL_LOCALES`
- :py:obj:`searx.locales.LOCALE_NAMES`
"""
# pylint: disable=invalid-name
from __future__ import annotations

from typing import Set
import json
from pathlib import Path

import babel
import babel.languages
import babel.core

from searx import searx_dir
import searx.locales

LOCALE_DATA_FILE = Path(searx_dir) / 'data' / 'locales.json'
TRANSLATIONS_FOLDER = Path(searx_dir) / 'translations'


def _descr(locale: babel.Locale) -> str:
    lang_descr_native: str = (locale.get_language_name(locale.language) or "").capitalize()
    lang_descr_en: str = (locale.get_language_name("en") or "").capitalize()
    return f"{lang_descr_native} ({lang_descr_en})"


def main():

    LOCALE_NAMES = {}
    RTL_LOCALES: Set[str] = set()

    for tag in searx.locales.TRANSLATION_BEST_MATCH:
        descr = LOCALE_NAMES.get(tag)
        if not descr:
            locale = babel.Locale.parse(tag, sep='-')
            tag = searx.locales.sxng_locale_tag(locale)
            LOCALE_NAMES[tag] = _descr(locale)
            if locale.text_direction == 'rtl':
                RTL_LOCALES.add(tag)

    for locale in searx.locales.get_translation_locales():
        tag = searx.locales.sxng_locale_tag(locale)
        descr = LOCALE_NAMES.get(tag)
        if not descr:
            LOCALE_NAMES[tag] = _descr(locale)
            if locale.text_direction == 'rtl':
                RTL_LOCALES.add(tag)

    content = {
        "LOCALE_NAMES": LOCALE_NAMES,
        "RTL_LOCALES": RTL_LOCALES,
    }

    with LOCALE_DATA_FILE.open('w', encoding='utf-8') as f:
        json.dump(content, f, indent=2, sort_keys=True, ensure_ascii=False)


if __name__ == "__main__":
    main()
