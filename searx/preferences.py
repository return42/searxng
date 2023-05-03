# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""Searx preferences implementation.
"""

# pylint: disable=useless-object-inheritance

from base64 import urlsafe_b64encode, urlsafe_b64decode
from zlib import compress, decompress
from urllib.parse import parse_qs, urlencode
from typing import Iterable, Dict, List, Set, Optional, Tuple
from collections import OrderedDict

import flask
import babel
import babel.core

from searx import get_setting, autocomplete, locales
from searx.enginelib import Engine
from searx.plugins import Plugin
from searx.engines import DEFAULT_CATEGORY

from searx import logger

logger = logger.getChild('preferences')

COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

UNSET_VALUES = ('', 'none', 'false', 'null')  # list of lowerkey strings
MAP_STR2BOOL = OrderedDict(
    # when one value maps to multiple keys, we need a ordering for the value to
    # key mapping.  THe string representation is normalized to the first
    # macthing boolean value ('0' or '1')
    ('0', False),
    ('1', True),
    ('on', True),
    ('off', False),
    ('true', True),
    ('false', False),
    ('', False),  # unset is mapped to False
    ('none', False),  # None is mapped to False
)


def is_locked(name: str):
    """Checks if a given setting name is locked by settings.yml"""
    lock: List = get_setting('preferences.lock')
    if not lock:
        return False
    return name in lock


class ValidationException(Exception):
    """Exption from ``cls.__init__`` when configuration value is invalid."""


class Setting:
    """Base class of user settings

    ``self.value`` :
        A python value (object). The string representation of this value is
        ``str(self)``.

    ``self.unset_values`` :
        A list of lowerkey strings like ``('', 'none', 'false', 'null')``.  By
        default, a setting is not nullable.  The value of a unset setting is
        ``None``.  The first item in the list is used for normalization of the
        string representation (:py:obj:`Setting.value_str`).

    ``self.locked`` : bool
        The setting is locked (:py:obj:`True`) or unlocked (:py:obj:`False`)

    """

    def __init__(
        self,
        default_value,  # any type that can be converted to a string
        locked: bool = False,
        unset_values: Optional[List[str]] = None,
    ):
        self.set_value(default_value)
        self.locked = locked
        self.unset_values = unset_values or []

    def value_str(self, value) -> str:
        """Returns the string representation of the value / can be used in HTML
        forms and cookies.

        If setting is *nullable* the string representation of the value is
        normalized to the first item in the ``self.unset_values`` list.

        If needed, its overwritten in the inheritance.

        """
        val_str = str(value)
        if self.unset_values and val_str.lower() in self.unset_values:
            return self.unset_values[0].lower()
        return val_str

    def parse_str(self, data: str):
        """Parse ``data`` string and return a *value* object.  Overwritten in
        the inheritance.

        """
        val_str = str(data)
        if self.unset_values and val_str.lower() in self.unset_values:
            return None
        return data

    def validate(self, value) -> bool:
        """Validates ``value``.  If invalid, a :py:obj:`ValidationException` is
        raised.  To be valid, a value and its string representation needs to be
        reversible (:py:obj:`Setting.value_str` & :py:obj:`Setting.parse_str`)::

            self.parse_str(value_str(value)) == value

        Overwritten in the inheritance.

        """
        try:
            val_str = self.value_str(value)
            val_obj = self.parse_str(val_str)

        except Exception as exc:
            raise ValidationException(f'string cast of {repr(value)} fails with: {exc}')

        if self.unset_values and val_str in self.unset_values:
            return True

        if val_obj != value:
            raise ValidationException(f'value {repr(value)} is not reversible <--> {repr(val_obj)}')

        return True

    def set_value(self, value):
        """Validates & set ``value``"""
        self.validate(value)
        self.value = value

    def parse(self, data: str) -> bool:
        """If setting is not *locked*, validate & set value from typecast of
        data string (see :py:obj:`self.parse_str`).  Returns ``False`` if locked
        and ``True`` if value is valid.

        """
        if self.locked:
            return False
        self.set_value(self.parse_str(data))
        return True

    def save(self, name: str, resp: flask.Response):
        """Set cookie ``name`` in HTTP response object, if setting is locked,
        leave reponse-cookie unset.

        If needed, its overwritten in the inheritance.

        """
        if not self.locked:
            resp.set_cookie(name, str(self), max_age=COOKIE_MAX_AGE)

    def __str__(self) -> str:
        return self.value_str(self.value)


class MapSetting(Setting):
    """Setting of a value that has to be translated in order to be storable"""

    def __init__(
        self,
        default_value,
        str2val: 'OrderedDict[str, object]',  # only mapping types are valid
        locked=False,
        unset_values: Optional[List[str]] = None,
    ):

        self.str2val = str2val
        super().__init__(default_value, locked, unset_values)

    def value_str(self, value) -> str:
        if self.unset_values and str(value).lower() in self.unset_values:
            return str(self.unset_values[0].lower())
        for k, val in self.str2val.items():
            if val == value:
                return k
        raise ValueError('value %s is not in: %s' % (value, self.str2val.values()))

    def parse_str(self, data: str):
        if self.unset_values and data.lower() in self.unset_values:
            return None
        return self.str2val[data]

    def validate(self, value) -> bool:
        if self.value_str(value) is None:
            raise ValidationException(f'Invalid value: {repr(value)}')
        return super().validate(value)


class BoolSetting(MapSetting):
    """Setting of a ``True`` / ``False`` value"""

    def __init__(self, default_val: bool, locked=False):
        super().__init__(default_val, MAP_STR2BOOL, locked)


class StringSetting(Setting):
    """Setting of plain string values"""

    def __init__(
        self,
        default_value: str,  # only string types are valid
        locked: bool = False,
        unset_values: Optional[List[str]] = None,
    ):
        super().__init__(default_value, locked, unset_values)

    def parse_str(self, data: str) -> Optional[str]:
        return str(super().parse_str(data))

    def validate(self, value: str) -> bool:
        if not isinstance(value, str):
            raise ValidationException(f'Invalid type: {repr(value)}')
        return super().validate(value)


class EnumStringSetting(StringSetting):
    """Setting of a value which can unset or come from the given catalog

    - unset_values: a list of lowerkey strings like ``('', 'none', 'false', 'null')``
    """

    def __init__(
        self,
        default_value: str,  # only string types are valid
        catalog: Iterable[str],
        locked: bool = False,
        unset_values: Optional[List[str]] = None,
    ):
        self.catalog = catalog
        super().__init__(default_value, locked, unset_values)

    def validate(self, value: str) -> bool:
        if self.value_str(value) not in self.catalog:
            raise ValidationException(f'Invalid value: "{value}"')
        return super().validate(value)


class SetStringSetting(Setting):
    """Setting of comma separated string values of type ``set``.

    Since the comma character is already used for separating in the string
    representation, the string values of the selection options must not contain
    a comma character.
    """

    def __init__(
        self,
        default_value: Set[str],  # only a set of string types are valid
        locked: bool = False,
        unset_values: Optional[List[str]] = None,
    ):

        super().__init__(default_value, locked, unset_values)

    def value_str(self, value) -> str:
        if self.unset_values and str(value).lower() in self.unset_values:
            return str(self.unset_values[0].lower())
        return ','.join(value)

    def parse_str(self, data: str) -> Optional[set]:
        if self.unset_values and data.lower() in self.unset_values:
            return None
        return {x.strip() for x in data.split(',')}

    def validate(self, value: Set[str]) -> bool:
        if not isinstance(value, Iterable):
            raise ValidationException(f'Invalid type: {repr(value)}')
        for item in self.value:
            if not isinstance(item, str):
                raise ValidationException(f'item is not a string type: {repr(item)}')
        return super().validate(value)


class MultipleChoiceSetting(SetStringSetting):
    """Setting of comma separated string values which can only come from the
    given catalog.  About limitations see :py:obj:`SetStringSetting`.

    """

    def __init__(
        self,
        default_value: Set[str],
        catalog: Iterable[str],
        locked: bool = False,
        unset_values: Optional[List[str]] = None,
    ):
        self.catalog = set(catalog)
        super().__init__(set(default_value), locked, unset_values)

    def validate(self, value: Set[str]) -> bool:
        if not isinstance(value, Iterable):
            raise ValidationException(f'Invalid type: {repr(value)}')
        for item in self.value:
            if self.value_str(item) not in self.catalog:
                raise ValidationException(f'Set contains invalid value: "{item}"')
        return super().validate(value)


class BoolGroup(dict):
    """A mapable group of boolean settings."""

    def __init__(self, group: str, defaults: Dict[str, bool]):
        super().__init__()
        self.group = group
        self.defaults = defaults

        self.key_enabled = f'enabled_{self.group}'
        self.key_disabled = f'disabled_{self.group}'

        for name, value in self.defaults.items():
            k = f'{self.group}_{name}'
            self[k] = BoolSetting(value)

    @property
    def enabled(self) -> List[str]:
        return [k for k, v in self.items() if v.value]

    @property
    def disable(self) -> List[str]:
        return [k for k, v in self.items() if not v.value]

    def set_values(self, name_list: List[str], value: bool):
        for name in name_list:
            k = f'{self.group}_{name}'
            if k in self:
                self[k].set_value(value)

    def parse(self, settings: Dict[str, str]):
        enabled = [x.strip() for x in settings.get(self.key_enabled, '').split(',')]
        self.set_values(enabled, True)

        disabled = [x.strip() for x in settings.get(self.key_disabled, '').split(',')]
        self.set_values(disabled, False)

    @property
    def modified(self) -> Tuple[Dict[str, BoolSetting], Dict[str, BoolSetting]]:
        """Tuple with enabled in first and disabled settings in second position."""
        enabled, disabled = {}, {}
        for name, default in self.defaults.items():
            k = f'{self.group}_{name}'
            value = self[k].value
            if default != value:
                if value:
                    enabled[name] = value
                else:
                    disabled[name] = value
        return enabled, disabled

    @property
    def settings(self) -> Dict[str, str]:
        enabled, disabled = self.modified
        enabled, disabled = ','.join(enabled.keys()), ','.join(disabled.keys())
        return {
            self.key_enabled: enabled,
            self.key_disabled: disabled,
        }

    def save(self, resp: flask.Response):
        for k, v in self.settings.items():
            resp.set_cookie(k, v, max_age=COOKIE_MAX_AGE)


class PluginGroup(BoolGroup):
    """Plugin settings"""

    def __init__(self, plugins: Iterable[Plugin]):

        defaults = {plugin.id: plugin.default_on for plugin in plugins}
        super().__init__('plugins', defaults)


class EngineCategoryGroup(BoolGroup):
    """Engine/Category settings.  Engines can be enabled/disabled per UI
    category, the ID of the setting is a combination of::

       {engine.name}__{ui-categoriy}

    """

    def __init__(self, engines: Iterable[Engine]):
        self.eng_cat: Dict[str, Set[str]] = {}
        defaults = {}
        ui_categories = list(get_setting('categories_as_tabs').keys()) + [DEFAULT_CATEGORY]

        for eng in engines:
            eng_name = eng.name
            c = set()

            for cat in eng.categories:
                c.add(cat)
                if cat in ui_categories:
                    defaults[f'{eng_name}__{cat}'] = not eng.disabled
            self.eng_cat[eng_name] = c

        super().__init__('engines', defaults)

    @property
    def enabled(self) -> Set[Tuple[str, str]]:
        enabled = set()
        for eng_name, categories in self.eng_cat:
            for cat in categories:
                item = self.get(f'{eng_name}__{cat}')
                if item and item.value:
                    enabled.add(cat)
        return enabled

    @property
    def disabled(self) -> Set[Tuple[str, str]]:
        disabled = set()
        for eng_name, categories in self.eng_cat:
            for cat in categories:
                item = self.get(f'{eng_name}__{cat}')
                if item and not item.value:
                    disabled.add(cat)
        return disabled

    def enabled_categories(self) -> Set[str]:
        return set(cat for _, cat in self.enabled)


class ClientPref:
    """Container to assemble client prefferences and settings."""

    # hint: searx.webapp.get_client_settings should be moved into this class

    locale: Optional[babel.Locale]
    """Locale prefered by the client."""

    def __init__(self, locale: Optional[babel.Locale] = None):
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
    def from_http_request(cls, http_request: flask.Request):
        """Build ClientPref object from HTTP request.

        - `Accept-Language used for locale setting
          <https://www.w3.org/International/questions/qa-accept-lang-locales.en>`__

        """
        al_header = http_request.headers.get("Accept-Language")
        if not al_header:
            return cls(locale=None)

        pairs = []
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
        pairs.sort(reverse=True, key=lambda x: x[1])
        return cls(locale=pairs[0][0])


class Preferences:
    """Validates and saves preferences to cookies"""

    def __init__(
        self,
        themes: List[str],
        categories: List[str],
        engines: Dict[str, Engine],
        plugins: Iterable[Plugin],
        client: Optional[ClientPref] = None,
    ):

        self.client = client or ClientPref()

        # pylint: disable=invalid-name
        CATALOG_DOI_RESOLVER = set(get_setting('doi_resolvers').keys())
        CATALOG_SEARCH_LOCALE = set(get_setting('search.languages'))
        CATALOG_UI_LOCALE = set(locales.LOCALE_NAMES.keys())
        CATALOG_AUTOCOMPLETE = set(autocomplete.backends.keys())
        CATALOG_SAVE_SEARCH = OrderedDict([('0', 0), ('1', 1), ('2', 2)])

        self.unknown_params: Dict[str, Setting] = {}
        self.engines = EngineCategoryGroup(engines=engines.values())
        self.plugins = PluginGroup(plugins=plugins)

        self.key_value_settings: Dict[str, Setting] = {
            'advanced_search': BoolSetting(get_setting('ui.advanced_search'), locked=is_locked('advanced_search')),
            'autocomplete': EnumStringSetting(
                get_setting('search.autocomplete'),
                locked=is_locked('autocomplete'),
                catalog=CATALOG_AUTOCOMPLETE,
                unset_values=UNSET_VALUES,
            ),
            'categories': MultipleChoiceSetting(
                ['general'], locked=is_locked('categories'), catalog=categories, unset_values=UNSET_VALUES
            ),
            'center_alignment': BoolSetting(get_setting('ui.center_alignment'), locked=is_locked('center_alignment')),
            'doi_resolver': MultipleChoiceSetting(
                get_setting('default_doi_resolver'), locked=is_locked('doi_resolver'), catalog=CATALOG_DOI_RESOLVER
            ),
            'image_proxy': BoolSetting(get_setting('server.image_proxy'), locked=is_locked('image_proxy')),
            'infinite_scroll': BoolSetting(get_setting('ui.infinite_scroll'), locked=is_locked('infinite_scroll')),
            # FIXME: language should renamed to search_locale
            'language': EnumStringSetting(
                get_setting('search.default_lang'),
                locked=is_locked('language'),
                catalog=CATALOG_SEARCH_LOCALE,
                unset_values=UNSET_VALUES,
            ),
            'method': EnumStringSetting(
                get_setting('server.method'), locked=is_locked('method'), catalog=('GET', 'POST')
            ),
            'query_in_title': BoolSetting(get_setting('ui.query_in_title'), locked=is_locked('query_in_title')),
            'results_on_new_tab': BoolSetting(
                get_setting('ui.results_on_new_tab'), locked=is_locked('results_on_new_tab')
            ),
            'safesearch': MapSetting(
                get_setting('search.safe_search'), locked=is_locked('safesearch'), str2val=CATALOG_SAVE_SEARCH
            ),
            'simple_style': EnumStringSetting(
                get_setting('ui.theme_args.simple_style'),
                locked=is_locked('simple_style'),
                catalog=['', 'auto', 'light', 'dark'],
            ),
            'theme': EnumStringSetting(get_setting('ui.default_theme'), locked=is_locked('theme'), catalog=themes),
            'tokens': SetStringSetting(set()),
            'ui_locale': EnumStringSetting(
                get_setting('ui.default_locale'),
                locked=is_locked('locale'),
                catalog=CATALOG_UI_LOCALE,
                unset_values=UNSET_VALUES,
            ),
        }

    @property
    def settings(self) -> Dict[str, str]:
        """Returns a dictionary where names of a setting are mapped to the
        string representation of the value / can be used in HTML forms and
        cookies.

        The returned value is a condensed version of the (modified) settings:

        1. The dictionary does not contain locked settings.
        2. From instances of :py:obj:`BoolGroup` only the enabled & disabled
           items are used (:py:obj:`BoolGroup.settings`).

        To get the python type of a value, use :py:obj:`Preferences.get_value`.

        """
        ret_val = {}
        for k, v in self.key_value_settings.items():
            if not v.locked:
                ret_val[k] = str(v)
        ret_val.update(self.engines.settings)
        ret_val.update(self.plugins.settings)
        return ret_val

    def parse_dict(self, input_data: Dict[str, str]):
        """parse preferences from request (``flask.request.form``)"""

        self.engines.parse(input_data)
        self.plugins.parse(input_data)

        for name, value in input_data.items():

            if name in self.key_value_settings:
                self.key_value_settings[name].parse(value)
            elif not any(name.startswith(x) for x in ['enabled_', 'disabled_']):
                self.unknown_params[name] = Setting(value)

    @property
    def url_params(self):
        """Return preferences as URL parameters"""
        return urlsafe_b64encode(compress(urlencode(self.settings).encode())).decode()

    def parse_encoded_data(self, input_data: str):
        """parse (base64) preferences from request (``flask.request.form['preferences']``)"""
        bin_data = decompress(urlsafe_b64decode(input_data))
        dict_data = {}
        for x, y in parse_qs(bin_data.decode('ascii'), keep_blank_values=True).items():
            dict_data[x] = y[0]
        self.parse_dict(dict_data)

    def get_value(self, name: str):
        """Returns the value for setting of ``name``"""

        for setting in [
            self.key_value_settings,
            self.engines,
            self.plugins,
            self.unknown_params,
        ]:
            item = setting.get(name)
            if item:
                return item.value

    def save(self, resp: flask.Response):
        """Save cookie in the HTTP response object"""
        self.engines.save(resp)
        self.plugins.save(resp)
        for name, setting in self.key_value_settings.items():
            setting.save(name, resp)
        for name, setting in self.unknown_params.items():
            setting.save(name, resp)

    @property
    def tokens(self):
        return self.key_value_settings['tokens'].value

    def validate_token(self, engine):
        valid = True
        if hasattr(engine, 'tokens') and engine.tokens:
            valid = bool(self.tokens.intersect(engine.tokens))
        return valid
