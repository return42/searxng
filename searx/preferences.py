# SPDX-License-Identifier: AGPL-3.0-or-later
"""SearXNG preferences implementation."""

import types
from collections import abc as c_abc

import babel
import babel.core

from . import prefs, plugins, forms
from searx import get_setting, autocomplete, favicons

from searx.enginelib import Engine
from searx.engines import DEFAULT_CATEGORY
from searx.extended_types import SXNG_Request
from searx.locales import LOCALE_NAMES
from searx.settings_defaults import SIMPLE_STYLE, SCHEMA
from searx.webutils import VALID_LANGUAGE_CODE


class ClientPref:
    """Container to assemble client prefferences and settings."""

    # hint: searx.webapp.get_client_settings should be moved into this class

    locale: babel.Locale | None
    """Locale preferred by the client."""

    def __init__(self, locale: babel.Locale | None = None):
        self.locale = locale

    @property
    def locale_tag(self):
        if self.locale is None:
            return None
        tag = self.locale.language
        if self.locale.territory:
            tag += '-' + self.locale.territory
        return tag

    @classmethod
    def from_http_request(cls, http_request: SXNG_Request):
        """Build ClientPref object from HTTP request.

        - `Accept-Language used for locale setting
          <https://www.w3.org/International/questions/qa-accept-lang-locales.en>`__

        """
        al_header = http_request.headers.get("Accept-Language")
        if not al_header:
            return cls(locale=None)

        pairs: list[tuple[babel.Locale, float]] = []
        for l in al_header.split(','):
            # fmt: off
            lang, qvalue = [_.strip() for _ in (l.split(';') + ['q=1',])[:2]]
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


class PlgGroup(prefs.OnOffGroup):
    """This class handles the active/inactive preferences of all plugins."""

    def __init__(self, grp_id: str, plg_list: c_abc.Sequence[plugins.PluginType]):
        dflt = forms.OnOffStruct()
        for plg in plg_list:
            if plg.active:
                dflt.enable(plg.id)
            else:
                dflt.disable(plg.id)
        super().__init__(grp_id=grp_id, locked=False, cfg=dflt)


class EngCtxGroup(prefs.OnOffGroup):
    """In this group of preferences, the status (active/inactive) of all engines
    is summarized.  The special thing about this group is that the status of an
    engine always has a context, the category. An engine can thus be active in
    one category and inactive in another.
    """

    def __init__(self, grp_id: str, eng_list: c_abc.Sequence[Engine | types.ModuleType]):
        dflt = forms.OnOffStruct()
        ui_categs: set[str] = set(get_setting("categories_as_tabs", {}).keys())  # type: ignore[reportAny]
        ui_categs.add(DEFAULT_CATEGORY)

        # An engine can be on/off in one or more categories of the UI.
        for eng in eng_list:
            for ctx in eng.categories:
                if not ctx in ui_categs:
                    continue
                if eng.disabled:
                    dflt.disable(eng.name, ctx)
                else:
                    dflt.enable(eng.name, ctx)
        super().__init__(grp_id=grp_id, locked=False, cfg=dflt)


def _languages_catalog() -> forms.Catalog[str]:
    def _validate(lang_tag: str) -> str:
        if lang_tag in extra or VALID_LANGUAGE_CODE.match(lang_tag):
            return lang_tag
        raise ValueError(f"invalid language code: '{lang_tag}'")

    extra = ["", "all", "auto"]
    ui_opts: list[str] = get_setting("search.languages")  # type: ignore[reportAny]
    return forms.Catalog(extra + ui_opts + [_validate])


class SXNGPrefs(prefs.PrefStorage):

    def __init__(
        self,
        theme_names: c_abc.Sequence[str],
        categ_names: c_abc.Sequence[str],
        eng_list: c_abc.Sequence[Engine | types.ModuleType],
        plg_list: c_abc.Sequence[plugins.PluginType],
        client: ClientPref | None = None,
    ):
        super().__init__()
        self.client: ClientPref = client or ClientPref()
        self.cfg: prefs.SettingsPref = get_setting("preferences")

        for plg in plg_list:
            self.register(plg.get_prefs())

        sxng_prefs: list[prefs.PrefType] = [
            # engine & plugin groups
            PlgGroup(grp_id="plg", plg_list=plg_list),
            EngCtxGroup(grp_id="eng", eng_list=eng_list),
            # search
            prefs.Pref(
                "language",
                locked="language" in self.cfg.lock,
                default=get_setting("search.default_lang"),  # type: ignore[reportAny]
                catalog=_languages_catalog(),
            ),
            prefs.Pref(
                "autocomplete",
                locked="autocomplete" in self.cfg.lock,
                default=get_setting("search.autocomplete"),  # type: ignore[reportAny]
                catalog=list(autocomplete.backends.keys()) + [""],
            ),
            prefs.Pref(
                "favicon_resolver",
                locked="favicon_resolver" in self.cfg.lock,
                default=get_setting("search.favicon_resolver"),  # type: ignore[reportAny]
                catalog=list(favicons.proxy.CFG.resolver_map.keys()) + [""],
            ),
            prefs.Pref(
                "safesearch",
                locked="safesearch" in self.cfg.lock,
                default=get_setting("search.safe_search"),  # type: ignore[reportAny]
                catalog={"": 0, "Moderate": 1, "Strict": 2},
            ),
            prefs.Pref(
                "categories",
                locked="categories" in self.cfg.lock,
                default=["general"],  # multiple select
                catalog=categ_names,
            ),
            # server
            prefs.Pref(
                "image_proxy",
                locked="image_proxy" in self.cfg.lock,
                default=get_setting("server.image_proxy"),  # type: ignore[reportAny]
                catalog=forms.ON_OFF,
            ),
            prefs.Pref(
                "method",
                locked="method" in self.cfg.lock,
                default=get_setting("method"),  # type: ignore[reportAny]
                catalog=SCHEMA["server"]["method"].type_definition,  # type: ignore[reportAny]
            ),
            # ui
            prefs.Pref(
                "locale",
                locked="locale" in self.cfg.lock,
                default=get_setting("ui.default_locale"),  # type: ignore[reportAny]
                catalog=list(LOCALE_NAMES.keys()) + [""],
            ),
            prefs.Pref(
                "theme",
                locked="theme" in self.cfg.lock,
                default=get_setting("ui.default_theme"),  # type: ignore[reportAny]
                catalog=theme_names,
            ),
            prefs.Pref(
                "results_on_new_tab",
                locked="results_on_new_tab" in self.cfg.lock,
                default=get_setting("ui.results_on_new_tab"),  # type: ignore[reportAny]
                catalog=forms.ON_OFF,
            ),
            prefs.Pref(
                "simple_style",
                locked="simple_style" in self.cfg.lock,
                default=get_setting("ui.theme_args.simple_style"),  # type: ignore[reportAny]
                catalog=SIMPLE_STYLE,
            ),
            prefs.Pref(
                "center_alignment",
                locked="center_alignment" in self.cfg.lock,
                default=get_setting("ui.center_alignment"),  # type: ignore[reportAny]
                catalog=forms.ON_OFF,
            ),
            prefs.Pref(
                "center_alignment",
                locked="center_alignment" in self.cfg.lock,
                default=get_setting("ui.center_alignment"),  # type: ignore[reportAny]
                catalog=forms.ON_OFF,
            ),
            prefs.Pref(
                "query_in_title",
                locked="query_in_title" in self.cfg.lock,
                default=get_setting("ui.query_in_title"),  # type: ignore[reportAny]
                catalog=forms.ON_OFF,
            ),
            prefs.Pref(
                "search_on_category_select",
                locked="search_on_category_select" in self.cfg.lock,
                default=get_setting("ui.search_on_category_select"),  # type: ignore[reportAny]
                catalog=forms.ON_OFF,
            ),
            prefs.Pref(
                "hotkeys",
                locked=False,
                default=get_setting("ui.hotkeys"),  # type: ignore[reportAny]
                catalog=SCHEMA["ui"]["hotkeys"].type_definition,  # type: ignore[reportAny]
            ),
            prefs.Pref(
                "url_formatting",
                locked=False,
                default=get_setting("ui.url_formatting"),  # type: ignore[reportAny]
                catalog=SCHEMA["ui"]["url_formatting"].type_definition,  # type: ignore[reportAny]
            ),
        ]
        self.register(sxng_prefs)


# pylint: disable=useless-object-inheritance

# from base64 import urlsafe_b64encode, urlsafe_b64decode
# from zlib import compress, decompress
# from urllib.parse import parse_qs, urlencode
# from collections import OrderedDict
# from collections.abc import Iterable

# import flask
# import babel
# import babel.core
# import msgspec


# MAP_STR2BOOL: dict[str, bool] = OrderedDict(
#     [
#         ('0', False),
#         ('1', True),
#         ('on', True),
#         ('off', False),
#         ('True', True),
#         ('False', False),
#         ('none', False),
#     ]
# )


# class ValidationException(Exception):
#     """Exption from ``cls.__init__`` when configuration value is invalid."""


# class Setting:
#     """Base class of user settings"""

#     def __init__(self, default_value: t.Any, locked: bool = False):
#         super().__init__()
#         self.value: t.Any = default_value
#         self.locked: bool = locked

#     def parse(self, data: str):
#         """Parse ``data`` and store the result at ``self.value``

#         If needed, its overwritten in the inheritance.
#         """
#         self.value = data

#     def get_value(self):
#         """Returns the value of the setting

#         If needed, its overwritten in the inheritance.
#         """
#         return self.value

#     def save(self, name: str, resp: flask.Response):
#         """Save cookie ``name`` in the HTTP response object

#         If needed, its overwritten in the inheritance."""
#         resp.set_cookie(name, self.value, max_age=COOKIE_MAX_AGE)


# class StringSetting(Setting):
#     """Setting of plain string values"""


# class EnumStringSetting(Setting):
#     """Setting of a value which can only come from the given choices"""

#     value: str

#     def __init__(self, default_value: str, choices: Iterable[str], locked: bool = False):
#         super().__init__(default_value, locked)
#         self.choices: Iterable[str] = choices
#         self._validate_selection(self.value)

#     def _validate_selection(self, selection: str):
#         if selection not in self.choices:
#             raise ValidationException('Invalid value: "{0}"'.format(selection))

#     def parse(self, data: str):
#         """Parse and validate ``data`` and store the result at ``self.value``"""
#         self._validate_selection(data)
#         self.value = data


# class MultipleChoiceSetting(Setting):
#     """Setting of values which can only come from the given choices"""

#     def __init__(self, default_value: list[str], choices: Iterable[str], locked: bool = False):
#         super().__init__(default_value, locked)
#         self.choices: Iterable[str] = choices
#         self._validate_selections(self.value)

#     def _validate_selections(self, selections: list[str]):
#         for item in selections:
#             if item not in self.choices:
#                 raise ValidationException('Invalid value: "{0}"'.format(selections))

#     def parse(self, data: str):
#         """Parse and validate ``data`` and store the result at ``self.value``"""
#         if data == '':
#             self.value: list[str] = []
#             return

#         elements = data.split(',')
#         self._validate_selections(elements)
#         self.value = elements

#     def parse_form(self, data: list[str]):
#         if self.locked:
#             return

#         self.value = []
#         for choice in data:
#             if choice in self.choices and choice not in self.value:
#                 self.value.append(choice)

#     def save(self, name: str, resp: flask.Response):
#         """Save cookie ``name`` in the HTTP response object"""
#         resp.set_cookie(name, ','.join(self.value), max_age=COOKIE_MAX_AGE)


# class SetSetting(Setting):
#     """Setting of values of type ``set`` (comma separated string)"""

#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.values: set[str] = set()

#     def get_value(self):
#         """Returns a string with comma separated values."""
#         return ','.join(self.values)

#     def parse(self, data: str):
#         """Parse and validate ``data`` and store the result at ``self.value``"""
#         if data == '':
#             self.values = set()
#             return

#         elements = data.split(',')
#         for element in elements:
#             self.values.add(element)

#     def parse_form(self, data: str):
#         if self.locked:
#             return

#         elements = data.split(',')
#         self.values = set(elements)

#     def save(self, name: str, resp: flask.Response):
#         """Save cookie ``name`` in the HTTP response object"""
#         resp.set_cookie(name, ','.join(self.values), max_age=COOKIE_MAX_AGE)


# class SearchLanguageSetting(EnumStringSetting):
#     """Available choices may change, so user's value may not be in choices anymore"""

#     value: str

#     def _validate_selection(self, selection: str):
#         if selection != '' and selection != 'auto' and not VALID_LANGUAGE_CODE.match(selection):
#             raise ValidationException('Invalid language code: "{0}"'.format(selection))

#     def parse(self, data: str):
#         """Parse and validate ``data`` and store the result at ``self.value``"""
#         if data not in self.choices and data != self.value:
#             lang = data.split('-', maxsplit=1)[0]

#             if data in self.choices:
#                 pass
#             elif lang in self.choices:
#                 data = lang
#             else:
#                 data = self.value
#         self._validate_selection(data)
#         self.value = data


# class MapSetting(Setting):
#     """Setting of a value that has to be translated in order to be storable"""

#     key: str
#     value: object

#     def __init__(
#         self, default_value: object, map: dict[str, object], locked: bool = False
#     ):  # pylint: disable=redefined-builtin
#         super().__init__(default_value, locked)
#         self.map: dict[str, object] = map

#         if self.value not in self.map.values():
#             raise ValidationException('Invalid default value')

#     def parse(self, data: str):
#         """Parse and validate ``data`` and store the result at ``self.value``"""

#         if data not in self.map:
#             raise ValidationException('Invalid choice: {0}'.format(data))
#         self.value = self.map[data]
#         self.key = data  # pylint: disable=attribute-defined-outside-init

#     def save(self, name: str, resp: flask.Response):
#         """Save cookie ``name`` in the HTTP response object"""
#         if hasattr(self, 'key'):
#             resp.set_cookie(name, self.key, max_age=COOKIE_MAX_AGE)


# class BooleanSetting(Setting):
#     """Setting of a boolean value that has to be translated in order to be storable"""

#     value: bool
#     key: str

#     def normalized_str(self, val: t.Any) -> str:
#         for v_str, v_obj in MAP_STR2BOOL.items():
#             if val == v_obj:
#                 return v_str
#         raise ValueError("Invalid value: %s (%s) is not a boolean!" % (repr(val), type(val)))

#     def parse(self, data: str):
#         """Parse and validate ``data`` and store the result at ``self.value``"""
#         self.value = MAP_STR2BOOL[data]
#         self.key = self.normalized_str(self.value)  # pylint: disable=attribute-defined-outside-init

#     def save(self, name: str, resp: flask.Response):
#         """Save cookie ``name`` in the HTTP response object"""
#         if hasattr(self, 'key'):
#             resp.set_cookie(name, self.key, max_age=COOKIE_MAX_AGE)


# class BooleanChoices:
#     """Maps strings to booleans that are either true or false."""

#     def __init__(self, name: str, choices: dict[str, bool], locked: bool = False):
#         self.name: str = name
#         self.choices: dict[str, bool] = choices
#         self.locked: bool = locked
#         self.default_choices: dict[str, bool] = dict(choices)

#     def transform_form_items(self, items):
#         return items

#     def transform_values(self, values):
#         return values

#     def parse_groups(self, data_disabled: str, data_enabled: str):
#         for disabled in data_disabled.split(','):
#             if disabled in self.choices:
#                 self.choices[disabled] = False

#         for enabled in data_enabled.split(','):
#             if enabled in self.choices:
#                 self.choices[enabled] = True

#     def parse_form(self, items: list[str]):
#         if self.locked:
#             return

#         disabled = self.transform_form_items(items)
#         for setting in self.choices:
#             self.choices[setting] = setting not in disabled

#     @property
#     def enabled(self):
#         return (k for k, v in self.choices.items() if v)

#     @property
#     def disabled(self):
#         return (k for k, v in self.choices.items() if not v)

#     def save(self, resp: flask.Response):
#         """Save cookie in the HTTP response object"""
#         disabled_changed = (k for k in self.disabled if self.default_choices[k])
#         enabled_changed = (k for k in self.enabled if not self.default_choices[k])
#         resp.set_cookie(
#             f"{COOKIE_PREFIX}disabled_{self.name}",
#             ",".join(disabled_changed),
#             max_age=COOKIE_MAX_AGE,
#         )
#         resp.set_cookie(
#             f"{COOKIE_PREFIX}enabled_{self.name}",
#             ",".join(enabled_changed),
#             max_age=COOKIE_MAX_AGE,
#         )

#     def get_disabled(self):
#         return self.transform_values(list(self.disabled))

#     def get_enabled(self):
#         return self.transform_values(list(self.enabled))


# class EnginesSetting(BooleanChoices):
#     """Engine settings"""

#     def __init__(self, engines: Iterable[Engine]):
#         choices: dict[str, bool] = {}
#         tab_categs: list[str] = list(get_setting("categories_as_tabs", {}).keys())
#         tab_categs.append(DEFAULT_CATEGORY)

#         for engine in engines:
#             for category in engine.categories:
#                 if not category in tab_categs:
#                     continue
#                 choices[f"{engine.name}__{category}"] = not engine.disabled
#         super().__init__("engines", choices)

#     def transform_form_items(self, items):
#         return [item[len('engine_') :].replace('_', ' ').replace('  ', '__') for item in items]

#     def transform_values(self, values):
#         if len(values) == 1 and next(iter(values)) == '':
#             return []
#         transformed_values = []
#         for value in values:
#             engine, category = value.split('__')
#             transformed_values.append((engine, category))
#         return transformed_values


# @t.final
# class Preferences:
#     """Validates and saves preferences to cookies"""

#     def __init__(
#         self,
#         themes: Iterable[str],
#         categories: Iterable[str],
#         engines: dict[str, Engine],
#         plg_storage: plugins.Storage,
#         client: ClientPref | None = None,
#     ):

#         super().__init__()

#         self.cfg: SettingsPref = get_setting("preferences")

#         self.key_value_settings: dict[str, Setting | plugins.PlgPrefType] = {
#             'categories': MultipleChoiceSetting(
#                 ["general"],
#                 locked="categories" in self.cfg.lock,
#                 choices=list(categories) + ["none"],
#             ),
#             'language': SearchLanguageSetting(
#                 get_setting("search.default_lang"),
#                 locked="language" in self.cfg.lock,
#                 choices=get_setting("search.languages") + [""],
#             ),
#             'locale': EnumStringSetting(
#                 get_setting("ui.default_locale"),
#                 locked="locale" in self.cfg.lock,
#                 choices=list(LOCALE_NAMES.keys()) + [""],
#             ),
#             'autocomplete': EnumStringSetting(
#                 get_setting("search.autocomplete"),
#                 locked="autocomplete" in self.cfg.lock,
#                 choices=list(autocomplete.backends.keys()) + [""],
#             ),
#             'favicon_resolver': EnumStringSetting(
#                 get_setting("search.favicon_resolver"),
#                 locked="favicon_resolver" in self.cfg.lock,
#                 choices=list(favicons.proxy.CFG.resolver_map.keys()) + [''],
#             ),
#             'image_proxy': BooleanSetting(
#                 get_setting("server.image_proxy"),
#                 locked="image_proxy" in self.cfg.lock,
#             ),
#             'method': EnumStringSetting(
#                 get_setting("server.method"),
#                 locked="method" in self.cfg.lock,
#                 choices=("GET", "POST"),
#             ),
#             'safesearch': MapSetting(
#                 get_setting("search.safe_search"),
#                 locked="safesearch" in self.cfg.lock,
#                 map={
#                     "0": 0,
#                     "1": 1,
#                     "2": 2,
#                 },
#             ),
#             'theme': EnumStringSetting(
#                 get_setting("ui.default_theme"),
#                 locked="theme" in self.cfg.lock,
#                 choices=themes,
#             ),
#             'results_on_new_tab': BooleanSetting(
#                 get_setting("ui.results_on_new_tab"),
#                 locked="results_on_new_tab" in self.cfg.lock,
#             ),
#             'simple_style': EnumStringSetting(
#                 get_setting("ui.theme_args.simple_style"),
#                 locked="simple_style" in self.cfg.lock,
#                 choices=["", "auto", "light", "dark", "black"],
#             ),
#             'center_alignment': BooleanSetting(
#                 get_setting("ui.center_alignment"),
#                 locked="center_alignment" in self.cfg.lock,
#             ),
#             'query_in_title': BooleanSetting(
#                 get_setting("ui.query_in_title"),
#                 locked="query_in_title" in self.cfg.lock,
#             ),
#             'search_on_category_select': BooleanSetting(
#                 get_setting("ui.search_on_category_select"),
#                 locked="search_on_category_select" in self.cfg.lock,
#             ),
#             'hotkeys': EnumStringSetting(
#                 get_setting("ui.hotkeys"),
#                 choices=["default", "vim"],
#             ),
#             'url_formatting': EnumStringSetting(
#                 get_setting("ui.url_formatting"),
#                 choices=["pretty", "full", "host"],
#             ),
#         }

#         self.plugins = PluginGroup(plg_storage=plg_storage)
#         for plg in plg_storage.plugin_list:
#             if plg.locked:
#                 continue
#             for pref_name, pref_item in plg.pref.items():
#                 if pref_name in self.key_value_settings:
#                     raise ValueError(f"There is already a preference called '{pref_name}'")
#                 self.key_value_settings[pref_name] = pref_item

#         self.engines = EnginesSetting(engines=engines.values())
#         self.tokens = SetSetting('tokens')
#         self.client = client or ClientPref()

#     def get_as_url_params(self):
#         """Return preferences as URL parameters"""
#         settings_kv: dict[str, str] = {}
#         for pref_name, pref_obj in self.key_value_settings.items():
#             if pref_obj.locked:
#                 continue
#             if isinstance(pref_obj, MultipleChoiceSetting):
#                 settings_kv[pref_name] = ",".join(pref_obj.get_value())
#             if isinstance(pref_obj, plugins.PlgPrefType):
#                 settings_kv[pref_name] = str(pref_obj)
#             else:
#                 settings_kv[pref_name] = pref_obj.get_value()

#         settings_kv['disabled_engines'] = ','.join(self.engines.disabled)
#         settings_kv['enabled_engines'] = ','.join(self.engines.enabled)

#         settings_kv['disabled_plugins'] = ','.join(self.plugins.disabled)
#         settings_kv['enabled_plugins'] = ','.join(self.plugins.enabled)

#         settings_kv['tokens'] = ','.join(self.tokens.values)

#         return urlsafe_b64encode(compress(urlencode(settings_kv).encode())).decode()

#     def parse_encoded_data(self, input_data: str):
#         """parse (base64) preferences from request (``flask.request.form['preferences']``)"""
#         bin_data = decompress(urlsafe_b64decode(input_data))
#         data: dict[str, str] = {}
#         for x, y in parse_qs(bin_data.decode("ascii"), keep_blank_values=True).items():
#             data[x] = y[0]
#         self.load_dict(data)

#     def set(self, pref_name: str, value: t.Any):
#         # cannot be used in case of engines or plugins
#         pref_obj = self.key_value_settings.get(pref_name)
#         if pref_obj is None:
#             raise ValueError(f"preference '{pref_name}' does not exists")

#         if isinstance(pref_obj, prefs.PrefItem):
#             pref_obj.set(value=value)
#         else:
#             pref_obj.value = value

#     def load_cookies(self, cookies: dict[str, str]):
#         user_prefs: dict[str, str] = {}
#         for c_name, c_val in cookies.items():
#             if c_name.startswith(COOKIE_PREFIX):
#                 user_prefs[c_name[len(COOKIE_PREFIX) :]] = c_val
#         if user_prefs:
#             self.load_dict(user_prefs)

#     def load_dict(self, data: dict[str, str]):
#         mem_data = {
#             "disabled_engines": "",
#             "enabled_engines": "",
#             "disabled_plugins": "",
#             "enabled_plugins": "",
#         }
#         for pref_name, pref_data in data.items():
#             pref_obj = self.key_value_settings.get(pref_name)
#             if isinstance(pref_obj, prefs.PrefItem):
#                 pref_obj.set_data(data=pref_data)

#             else:
#                 if pref_obj is not None:
#                     pref_obj.parse(data=pref_data)
#                 else:
#                     if mem_data.get(pref_name) is not None:
#                         # self.plugins.parse_cookie & self.engines.parse_cookie
#                         mem_data[pref_name] = pref_data
#                     elif pref_name == "tokens":
#                         self.tokens.parse(pref_data)

#         self.plugins.parse_groups(mem_data["disabled_plugins"], mem_data["enabled_plugins"])
#         self.engines.parse_groups(mem_data["disabled_engines"], mem_data["enabled_engines"])

#     def load_form(self, form_data: dict[str, str]):
#         # Boolean preferences are not sent by the form if they're false, so we
#         # have to add them as "False" manually if they're not sent.
#         field_names: Iterable[str] = form_data.keys()
#         pref_names: Iterable[str] = self.key_value_settings.keys()

#         for pref_name, pref_obj in self.key_value_settings.items():
#             if pref_name not in field_names and isinstance(pref_obj, (BooleanSetting, plugins.PrefBool)):
#                 form_data[pref_name] = "False"

#         user_prefs: dict[str, str] = {
#             "disabled_engines": "",
#             "enabled_engines": "",
#             "disabled_plugins": "",
#             "enabled_plugins": "",
#             "categories": "",
#         }

#         for field_name, field_val in form_data.items():
#             if field_name in pref_names:
#                 user_prefs[field_name] = field_val
#                 continue

#             # the following fields are comming from the preferences form ..

#             if field_name.startswith("category_") and field_val == "on":
#                 _name = field_name[len("category_") :]
#                 user_prefs["categories"] += f", {_name}"
#                 continue

#             if field_name.startswith("plugin_"):
#                 _name = field_name[len("plugin_") :]
#                 if field_val == "on":
#                     user_prefs["enabled_plugins"] += f", {_name}"
#                     continue
#                 if field_val == "off":
#                     user_prefs["disabled_plugins"] += f", {_name}"
#                     continue

#             if field_name.startswith("engine_"):
#                 _name = field_name[len("engine_") :]
#                 if field_val == "on":
#                     user_prefs["enabled_engines"] += f", {_name}"
#                     continue
#                 if field_val == "off":
#                     user_prefs["disabled_engines"] += f", {_name}"
#                     continue

#             if field_name in (
#                 # FIXME: see HTML macro tab_header
#                 "maintab",
#                 "enginetab",
#                 # b64encode preferences
#                 "preferences",
#             ):
#                 continue
#             raise NotImplementedError(f"can't process form data: {field_name} = {field_val}")

#     # cannot be used in case of engines or plugins
#     def get_value(self, pref_name: str) -> t.Any:
#         """Returns the serialized value for ``pref_name`` or ``None`` if
#         preference does not exist."""

#         pref_obj = self.key_value_settings.get(pref_name)
#         if pref_obj is None:
#             return None
#         if isinstance(pref_obj, prefs.PrefItem):
#             return pref_obj.value
#         return pref_obj.get_value()

#     def save(self, resp: flask.Response):
#         """Save cookie in the HTTP response object"""
#         for pref_name, pref_obj in self.key_value_settings.items():
#             cookie_name = f"{COOKIE_PREFIX}{pref_name}"
#             if pref_obj.locked:
#                 continue
#             if isinstance(pref_obj, prefs.PrefItem):
#                 resp.set_cookie(cookie_name, str(pref_obj), max_age=COOKIE_MAX_AGE)
#             else:
#                 pref_obj.save(cookie_name, resp)
#         self.engines.save(resp)
#         self.plugins.save(resp)
#         self.tokens.save('tokens', resp)
#         return resp

#     def validate_token(self, engine):
#         valid = True
#         if hasattr(engine, 'tokens') and engine.tokens:
#             valid = False
#             for token in self.tokens.values:
#                 if token in engine.tokens:
#                     valid = True
#                     break

#         return valid
