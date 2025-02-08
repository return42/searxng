# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, cyclic-import
"""Stuff to implement input forms."""

from __future__ import annotations

__all__ = ["Form", "Field", "FieldABC", "SingleChoice", "Bool", "SearchLocale", "MultipleChoice", "BoolGrp"]

import abc
import json
import typing

from base64 import urlsafe_b64encode, urlsafe_b64decode
from zlib import compress, decompress
from collections.abc import Sequence

import flask
from flask_babel import gettext

import searx.locales
from searx import get_setting
from searx.sxng_locales import sxng_locales
from searx.extended_types import sxng_request

COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 5  # 5 years
UNKNOWN = object()


class FieldABC(abc.ABC):
    """Abstract base class of all types of input fields of a form."""

    name: str
    """Name of *this* preference. The ``name`` is used in ``id`` and ``name``
    attributes in the corresponding HTML element and should therefore not have
    any special characters. Example (:py:obj:`FieldABC.field_id`):

    .. code:: html

       <input name="{field_name}{sep}{name}" id="{field_name}{sep}{name}">

    """

    ui_class: str

    value: typing.Any
    """Current value for *this* input item."""

    default: typing.Any
    """Default value for *this* input item."""

    cookie_prefix: str
    """Prefix of the cookie of *this* input item."""

    cookie_name: str
    """Name of the cookie for *this* input item."""

    locked: bool = False
    """``True`` when input item is locked (:ref:`settings preferences`)."""

    form_id: str = "form"
    """The ``form_id`` is used in ``id`` and ``name`` attributes in the
    corresponding HTML elements (e.g. form_, fieldset_, ..) and should therefore
    not have any special characters.

    _form: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/form#name
    _fieldset: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/fieldset#form
    """

    sep: str = "»"
    """Separator used to form the *name* (id, ..) of components used in a form_."""

    def __init__(
        self,
        name: str,
        default: typing.Any,
        description: str = "",
        legend: str = "",
        cookie_prefix: str = "sxng_",
        ui_class: str = "",
    ):
        self.name = name
        self.ui_class = ui_class
        self.default = default
        self.description = description
        self.legend = legend
        self.cookie_prefix = cookie_prefix
        self.locked = False

        if getattr(self, "cookie_name", None) is None:
            self.cookie_name = f"{self.cookie_prefix}{self.name}"
        if getattr(self, "value", None) is None:
            self.value = self.str2val(self.val2str(default))

    @property
    def str(self):
        """String value of the *value*"""
        return self.val2str(self.value)

    def lock(self):
        self.locked = True

    def unlock(self):
        self.locked = False

    def val2str(self, value):
        """Convert typed value to string value.

        .. attention::

           If a typed value can have multiple string representations (in the
           inheritances), then this method must perform a normalization to one
           string representation.
        """
        return str(value)

    def str2val(self, string: str):
        """Convert string value to typed value."""
        return type(self.default)(string)

    def validate(self, string: str):
        """Raise a :py:obj.`ValueError` if string value isn't valid."""
        v = self.str2val(string)
        if self.val2str(v) != string:
            raise ValueError(
                f"The string '{string}' can't be converted from string to"
                f" {type(self.default).__name__} value without loss: {v}"
            )

    @abc.abstractmethod
    def serializable(self, mod_only: bool = True) -> dict[str, str] | None:
        """Serializable representation of this preference.  A dictionary of
        *this* preference with a string value.  The dictionary can be:

        - passed to :py:obj:`FieldABC.parse_form`
        - serialized to JSON (or any other string de-serializer)

        With ``mod_only`` set to ``True`` only values are returned if they have
        been changed / differ from the default value.
        """

    @abc.abstractmethod
    def parse_form(self, fields: dict[str, str]):
        """Parse dict from the input fields of a HTML ``<form>`` element and set
        *this* property.
        """

    @abc.abstractmethod
    def save_cookie(self, resp: flask.Response, max_age: int = COOKIE_MAX_AGE):
        """Save modified preference in a cookie of the HTTP response object.  In
        cases where the user has not made any changes to the default value, no
        cookie is required and is therefore not set.

        Keep in mind: :py:obj:`Preference.val2str` can be used to normalize a
        string value!  As long as the string representation of value is
        identical, the setting remains unchanged at the default value!
        """

    @abc.abstractmethod
    def parse_cookies(self, cookies: dict[str, str]):
        """Parse the dict from :py:obj:`flask.Request.cookies` and set *this*
        property to value of the cookie named :py:obj:`Preference.cookie_name`.
        """


class Field(FieldABC):
    """Base class to map a field (string type) from a HTTP request of a
    submitted ``<form>`` element to the typed value on server side (vice versa).
    The ``name`` is used in the ``id`` and ``name`` attribute in the
    corresponding HTML element and should therefore not have any special
    characters.

    .. code:: html

       <input name="..{name}.. " id="..{name}..">

    This base class is suitable for base types such as ``str``, ``int`` or
    ``float``.  Inheritances are available for the implementation of other and
    more complex types such as catalogs.
    """

    def field_id(self) -> str:
        """Returns an ID suitable to use as element ``id`` in a form field."""
        return self.sep.join([self.form_id, self.name])

    def get(self) -> str:
        """Returns string value of *this* field."""
        return self.val2str(self.value)

    def set(self, string):
        """If *this* field is not *locked*, parse the string value (from a
        form field) and store the typed result at :py:obj:`Preference.value`.
        """
        if self.locked:
            return
        self.validate(string)
        self.value = self.str2val(string)

    # ABC methods ..

    def serializable(self, mod_only: bool = True) -> dict[str, str] | None:
        string = self.val2str(self.value)
        if not mod_only or string != self.val2str(self.default):
            return {self.field_id(): string}
        return None

    def parse_form(self, fields: dict[str, str]):
        string = fields.get(self.field_id(), None)
        if string is not None:
            self.set(string)

    def save_cookie(self, resp: flask.Response, max_age: int = COOKIE_MAX_AGE):
        string = self.val2str(self.value)
        if string != self.val2str(self.default):
            resp.set_cookie(self.field_id(), string, max_age=max_age)

    def parse_cookies(self, cookies: dict[str, str]):
        string = cookies.get(self.field_id(), None)
        if string is not None:
            self.set(string)


class SingleChoice(Field):
    """Class suitable for the implementation of catalogs from which a choice can
    be made.  One value can be selected and the string value is mapped to a
    typed value via a mapping table.
    """

    str2obj: dict[str, typing.Any]

    def __init__(
        self,
        name: str,
        default: typing.Any,
        catalog: dict[str, typing.Any] | Sequence[typing.Any] | set[typing.Any],
        description: str = "",
        legend: str = "",
        catalog_descr: dict[str, str] = {},
        ui_class: str = "",
    ):
        super().__init__(
            name=name,
            default=default,
            description=description,
            legend=legend,
            ui_class=ui_class,
        )

        if isinstance(catalog, (Sequence, set)):
            self.str2obj = {str(i): i for i in catalog}
        else:
            self.str2obj = catalog
        self.catalog_descr = catalog_descr

    def val2str(self, value) -> str:
        for s, o in self.str2obj:
            if value == o:
                return s
        raise ValueError(f"typed value {value} is unknown to the mapping table.")

    def str2val(self, string: str) -> typing.Any:
        val = self.str2obj.get(string, UNKNOWN)
        if val == UNKNOWN:
            raise ValueError(f"string value {string} is unknown to the mapping table.")
        return val

    def validate(self, string: str):
        self.str2val(string)

    def menu_options(self) -> typing.Generator[tuple[str, bool, str]]:
        """Iterator suitable to generate a list of options.  Returns a three
        digit tuple::

            ( {{value}}, {{selected}}, {{description}} )

            <option value="{{value}}" {% if selected %} selected="selected" {% endif %}>{{description}}</option>

        """
        selected = self.val2str(self.value)
        for str_val in self.str2obj:
            yield (str_val, str_val == selected, self.catalog_descr.get(str_val, gettext(str_val)))


class Bool(SingleChoice):
    """Class suitable for the implementation on/off switches."""

    value = bool
    default = bool

    def __init__(
        self,
        name: str,
        default: bool,
        description: str = "",
        legend: str = "",
        true: str = "True",
        false: str = "False",
        ui_class: str = "",
    ):
        super().__init__(
            name=name,
            default=default,
            catalog={true: True, false: False},
            description=description,
            legend=legend,
            ui_class=ui_class,
        )


class SearchLocale(SingleChoice):

    def __init__(
        self,
        name: str,
        description: str = "",
        legend: str = "",
        auto_locale: str = "auto",
        ui_class: str = "",
    ):

        special_locales: tuple[tuple[str, str, str, str, str], ...] = (
            ("all", gettext("Default language") + " [all]", "", "", ""),
            ("auto", gettext("Auto-detect") + f" [{auto_locale}]", "", "", ""),
        )
        catalog = set()
        catalog_descr = {}
        allowed_tags = get_setting("search.languages")

        for sxng_tag, lang_name, country_name, _, flag in special_locales + sxng_locales:
            if sxng_tag in allowed_tags:
                catalog.add(sxng_tag)
                catalog_descr[sxng_tag] = " ".join(filter(None, [lang_name, country_name, flag]))

        default = searx.locales.match_locale(sxng_request.client.search_locale_tag, allowed_tags, fallback=self.default)
        super().__init__(
            name=name,
            default=default,
            catalog=catalog,
            description=description,
            legend=legend,
            catalog_descr=catalog_descr,
            ui_class=ui_class,
        )


class MultipleChoice(FieldABC):
    """Class suitable for the implementation of catalogs from which a multiple
    choice can be made.  None, one ore more value can be selected and the string
    values are mapped to a typed values via a mapping table.
    """

    value = set[typing.Any]
    default = set[typing.Any]
    str2obj: dict[str, typing.Any]

    def __init__(
        self,
        name: str,
        default: set[typing.Any],
        catalog: dict[str, typing.Any] | Sequence[typing.Any] | set[typing.Any],
        description: str = "",
        legend: str = "",
        catalog_descr: dict[str, str] = {},
        ui_class: str = "",
    ):
        # just to verify the defaults are in catalog
        for val in default:
            self.val2str(val)
        self.value = default

        super().__init__(
            name=name,
            default=default,
            description=description,
            legend=legend,
            ui_class=ui_class,
        )

        if isinstance(catalog, (Sequence, set)):
            self.str2obj = {str(i): i for i in catalog}
        else:
            self.str2obj = catalog
        self.catalog_descr = catalog_descr

    def menu_options(self) -> typing.Generator[tuple[str, bool, str]]:
        """Iterator suitable to generate a list of options.  Returns a three
        digit tuple::

            ( {{value}}, {{selected}}, {{description}} )

            <option value="{{value}}" {% if selected %} selected="selected" {% endif %}>{{description}}</option>

        """
        selected = [self.val2str(x) for x in self.value]
        for str_val in self.str2obj:
            yield (str_val, str_val in selected, self.catalog_descr.get(str_val, gettext(str_val)))

    @property
    def str(self):
        """String value of the *value*"""
        return ",".join([self.str2val(v) for v in self.value])

    @property
    def catalog_id(self) -> str:
        return self.sep.join([self.form_id, self.name])

    def item_id(self, item_name) -> str:
        return self.sep.join([self.form_id, self.name, item_name])

    def val2str(self, value) -> str:
        for s, o in self.str2obj:
            if value == o:
                return s
        raise ValueError(f"typed value {value} is unknown to the mapping table.")

    def str2val(self, string: str) -> typing.Any:
        val = self.str2obj.get(string, UNKNOWN)
        if val == UNKNOWN:
            raise ValueError(f"string value {string} is unknown to the mapping table.")
        return val

    # ABC methods ..

    def serializable(self, mod_only: bool = True) -> dict[str, str] | None:
        if mod_only and self.value == self.default:
            return None
        fields = {}
        for item_name, item_value in self.str2obj.items():
            fields[self.item_id(item_name)] = self.val2str(item_value)
        return fields

    def parse_form(self, fields: dict[str, str]):
        new_val = set()
        for item_name in self.str2obj:
            string = fields.get(self.item_id(item_name))
            if string is not None:
                new_val.add(self.val2str(string))
        self.value = new_val

    def save_cookie(self, resp: flask.Response, max_age: int = COOKIE_MAX_AGE):
        d = self.serializable()
        if not d:
            return
        cookie_str = self.sep.join([self.val2str(i) for i in self.value])
        if cookie_str:
            resp.set_cookie(self.catalog_id, cookie_str, max_age=max_age)

    def parse_cookies(self, cookies: dict[str, str]):
        cookie_str = cookies.get(self.catalog_id, None)
        if cookie_str is None:
            return
        new_val = set()
        for item_string in cookie_str.split(self.sep):
            new_val.add(self.str2val(item_string))
        self.value = new_val


class BoolGrp(abc.ABC):
    """Abstract base class to group :py:obj:`Bool` fields."""

    sep = FieldABC.sep
    form_id = FieldABC.form_id

    grp_name: str
    """Name of *this* group."""

    members: dict[str, Bool]
    """Fields in *this* group."""

    def __init__(self, form_id: str, grp_name: str):
        self.form_id = form_id
        self.grp_name = grp_name
        self.members = {}

    @property
    def group_prefix(self):
        return self.sep.join([self.form_id, self.grp_name])

    def parse_form(self, input_fields: dict[str, str]):
        """Parse dict from the input fields of a HTML ``<form>`` element and set
        the members of *this* group to values of the fields with prefix
        :py:obj:`Preference.grp_prefix`.
        """
        for field_id in input_fields.keys():
            if not field_id.startswith(self.group_prefix):
                continue
            for field in self.members.values():
                field.parse_form(input_fields)

    def serializable(self, mod_only: bool = True) -> dict[str, str] | None:
        fields = {}
        for field in self.members.values():
            s = field.serializable(mod_only)
            if not s:
                continue
            fields.update(s)
        return fields

    def save_cookie(self, resp: flask.Response, max_age: int = COOKIE_MAX_AGE):
        _on = set()
        _off = set()
        for member_name, field in self.members.items():
            s = field.serializable()
            if not s or (field.val2str(field.value) == field.val2str(field.default)):
                continue
            if field:
                _on.add(member_name)
            else:
                _off.add(member_name)
        if _on:
            resp.set_cookie(f"{self.group_prefix}_on", self.sep.join(_on), max_age=max_age)
        if _off:
            resp.set_cookie(f"{self.group_prefix}_off", self.sep.join(_off), max_age=max_age)

    def parse_cookies(self, cookies: dict[str, str]):
        for member_name in cookies.get(f"{self.group_prefix}_on", "").split(self.sep):
            self.members[member_name].value = True
        for member_name in cookies.get(f"{self.group_prefix}_off", "").split(self.sep):
            self.members[member_name].value = False


class Form:
    """A component to implement forms."""

    form_id = FieldABC.form_id

    def __init__(self, form_id, fields: list[FieldABC | BoolGrp]):
        self.form_id = form_id
        self.components: dict[str, FieldABC | BoolGrp]
        for field in fields:
            if isinstance(field, FieldABC):
                field.form_id = self.form_id
                self.components[field.name] = field
                continue
            if isinstance(field, BoolGrp):
                self.components[field.grp_name] = field
                continue
            raise ValueError(f"unknow field type {type(field)}")

    def __getitem__(self, comp_name):
        return self.components[comp_name]

    def lock(self, field_names: list[str]):
        for field in [self.components[name] for name in field_names]:
            if isinstance(field, FieldABC):
                field.lock()

    def unlock(self, field_names: list[str]):
        for field in [self.components[name] for name in field_names]:
            if isinstance(field, FieldABC):
                field.unlock()

    def parse_form(self, form_fields: dict[str, str]):
        for comp in self.components.values():
            comp.parse_form(form_fields)

    def parse_cookies(self, cookies: dict[str, str]):
        for comp in self.components.values():
            comp.parse_cookies(cookies)

    def save_cookies(self, resp: flask.Response, max_age: int = COOKIE_MAX_AGE):
        for comp in self.components.values():
            comp.save_cookie(resp, max_age)

    def serializable(self, mod_only: bool = True) -> dict[str, str] | None:
        fields = {}
        for comp in self.components.values():
            s = comp.serializable(mod_only)
            if not s:
                continue
            fields.update(s)
        return fields

    def is_locked(self, comp_name: str) -> bool:
        """Returns lock state True/False of the component ``comp_name``."""
        comp = self.components[comp_name]
        if isinstance(comp, BoolGrp):
            # there is no lock for members of BoolGrp
            return True
        return comp.locked

    def value(self, comp_name: str) -> typing.Any:
        """Returns value of the component ``comp_name``."""
        comp = self.components[comp_name]
        if isinstance(comp, BoolGrp):
            # in case of BoolGrp return field names and their values
            return comp.members
        return comp.value

    def str(self, comp_name: str) -> str | dict[str, str]:
        """Returns string value of the component ``comp_name``."""
        comp = self.components[comp_name]
        if isinstance(comp, BoolGrp):
            # in case of BoolGrp return field names and their values
            return {name: field.str for name, field in comp.members.items()}
        return comp.str

    @property
    def pref_url_params(self):  # FIXME rename to url_b64encode
        """Preferences as URL parameters (base64)."""
        prefs = self.serializable()
        data_str = json.dumps(prefs)
        return urlsafe_b64encode(compress(data_str.encode())).decode()

    def parse_encoded_data(self, base64_url: str):  # FIXME rename to url_b64decode
        """Parse (base64) preferences from request
        (``flask.request.form["pref_url_params"]``)"""

        data_str = decompress(urlsafe_b64decode(base64_url))
        fields = json.loads(data_str)
        self.parse_form(fields)
