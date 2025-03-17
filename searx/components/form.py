# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, cyclic-import
"""Stuff to implement input forms."""

from __future__ import annotations
import dataclasses

__all__ = [
    "Bool",
    "BoolGrp",
    "Field",
    "FieldABC",
    "FieldCollection",
    "Form",
    "MultipleChoice",
    "SingleChoice",
]

import abc
import json
import typing

from base64 import urlsafe_b64encode, urlsafe_b64decode
from zlib import compress, decompress
from collections.abc import Sequence, MutableMapping, Iterable

import babel.numbers
from flask_babel import lazy_gettext
from flask_babel.speaklater import LazyString

from searx.extended_types import SXNG_Request, SXNG_Response, sxng_request

COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 5  # 5 years
UNKNOWN = object()

# JSONType =  str|int|float|bool|None|typing.Mapping[str,str|int|float|bool|None] |Iterable[str|int|float|bool|None] | None

SerializableType = str | list[str] | dict[str, str | list[str] | dict[str, str]] | None


class FieldABC(abc.ABC):
    """Abstract base class of all types of input fields of a form."""

    name: str
    """Name of *this* preference. The ``name`` is used in ``id`` and ``name``
    attributes in the corresponding HTML element and should therefore not have
    any special characters. Example (:py:obj:`FieldABC.field_id`):

    .. code:: html

       <input name="{field_name}{sep}{name}" id="{field_name}{sep}{name}">
    """

    default: str | list[str]
    """Default string value for *this* input item.  If the input represents a
    string value, then the default must be a string.  However, if the input
    field represents several values, e.g. for multiple choice inputs, then the
    default must be a list."""

    str_sep: str = ","
    """If the input field can carry a list of values, then the values are
    separated from each other by this character in the string representation."""

    str2obj: MutableMapping[str, typing.Any] | Iterable[str] | typing.Callable[[str], typing.Any]
    """A table to map a string value to a python object or a catalog of strings
    (catalog of choices).  Alternatively, factory method or a type such as
    ``int``, ``float`` .. can be used, the default is ``str``."""

    value: typing.Any
    """Typed value for *this* input item."""

    locked: bool = False
    """``True`` when input item is locked (:ref:`settings preferences`)."""

    sep: str = "»"
    form_id: str = "form"
    ui_class: str = ""

    def __init__(
        self,
        name: str,
        default: str | list[str],
        str2obj: MutableMapping[str, typing.Any] | Iterable[str] | typing.Callable[[str], typing.Any] = str,
        description: LazyString | str = "",
        legend: LazyString | str = "",
        ui_class: str = "",
    ):

        self.name = name
        self.ui_class = ui_class
        self.description = description
        self.legend = legend
        self.locked = False

        if getattr(self, "str2obj", UNKNOWN) is UNKNOWN:
            self.str2obj = str2obj

        if getattr(self, "default", UNKNOWN) is UNKNOWN:
            # just to validate ..
            value = self.str2val(default)
            self.default = default
            if getattr(self, "value", UNKNOWN) is UNKNOWN:
                self.value = value

        if getattr(self, "value", UNKNOWN) is UNKNOWN:
            self.value = self.str2val(self.default)

        if isinstance(self.default, list):
            self.default.sort()

            # The string values must not contain the separator character
            for string in self.default:
                if self.str_sep in string:
                    raise ValueError(f"Invalid separator '{self.str_sep}' in default string '{string}'")
            if isinstance(self.str2obj, (MutableMapping, Iterable)):
                for string in self.str2obj:
                    if self.str_sep in string:
                        raise ValueError(f"Invalid separator '{self.str_sep}' in catalog value '{string}'")

    def str2val(self, string: str | list[str]) -> typing.Any | list[typing.Any]:
        """Typcast of a string to a python object/value.  The function can also
        be used to validate a string value."""

        str_list = string
        if isinstance(string, str):
            str_list = [string]

        val_set: set[typing.Any] = set()

        if isinstance(self.str2obj, MutableMapping):
            # the catalog is a table that maps a string to a python object
            for string in str_list:
                value = self.str2obj.get(string, UNKNOWN)
                if value is UNKNOWN:
                    raise ValueError(f"string value '{string}' is unknown to the catalog.")
                val_set.add(value)

        elif isinstance(self.str2obj, Iterable):
            # the catalog is a list/set of strings -> the string has to be
            # in the catalog (string-value and typed-value are both str)
            for string in str_list:
                if string not in self.str2obj:
                    raise ValueError(f"string value '{string}' is unknown to the catalog.")
                val_set.add(string)

        else:
            # self.str2obj is a type or a factory.  The forward / backward
            # conversion must be possible and unambiguous; if this is not the
            # case, the typecast would result in a loss of information.
            for string in str_list:

                if self.str2obj is float:
                    value = float(
                        babel.numbers.parse_decimal(string, sxng_request.client.locale, numbering_system="latn")
                    )
                else:
                    value = self.str2obj(string)
                    if str(value) != string:
                        raise ValueError(
                            f"The typcast from string '{string}' to type {self.str2obj}"
                            f" is not possible without loss: {repr(value)}"
                        )
                val_set.add(value)

        if isinstance(self.default, list):
            return list(val_set)
        return val_set.pop()

    def val2str(self, value: typing.Any) -> str | list[str]:
        """Typcast of a python object/value to a string (or a list of values to
        a list of strings).

        .. attention::

           If a typed value can have multiple string representations (in the
           inheritances), then this method must perform a normalization to one
           string representation.

        """

        val_list = [value]

        # Whether the input value is a list of values or the value of the input
        # internally represents a list depends on whether the default itself is
        # a list or only represents a value (which might be a list internally).

        if isinstance(self.default, list) and isinstance(value, list):
            # the input value is a list of values!
            val_list = value

        str_set: set[str] = set()

        if isinstance(self.str2obj, MutableMapping):
            # the catalog is a table that maps a string to a python object
            for value in val_list:
                str_val: str = UNKNOWN  # type: ignore
                for k, v in self.str2obj.items():
                    if v == value:
                        str_val = k
                        break
                if str_val is UNKNOWN:
                    raise ValueError(f"typed value {repr(value)} is unknown to the catalog.")
                str_set.add(str_val)

        elif isinstance(self.str2obj, Iterable):
            # the catalog is a list/set of strings -> the value has to be
            # in the catalog (string-value and typed-value are both str)
            for value in val_list:
                if value not in self.str2obj:
                    raise ValueError(f"typed value '{value}' is unknown to the catalog.")
                str_set.add(value)

        else:
            # self.str2obj is a type or a factory.  The forward / backward
            # conversion must be possible and unambiguous; if this is not the
            # case, the typecast would result in a loss of information.
            for value in val_list:

                if self.str2obj is float:
                    str_val = babel.numbers.format_number(value, sxng_request.client.locale)
                else:
                    str_val = str(value)
                    if self.str2obj(str_val) != value:
                        raise ValueError(
                            f"The typcast from value {repr(value)} of type {self.str2obj}"
                            f" to string is not possible without loss: '{str_val}'"
                        )
                str_set.add(str_val)

        if isinstance(self.default, list):
            return list(str_set)
        return str_set.pop()

    def set(self, string: str | list[str] | set[str]):
        """If *this* field is not *locked*, parse the string value (from a
        form field) and store the typed result at :py:obj:`Preference.value`.
        """
        if self.locked:
            return

        if isinstance(self.default, (list, set)):
            # default is type list --> string value must also be of type list
            if isinstance(string, str):
                # build a str list from string
                string = [x.strip() for x in string.split(self.str_sep)]
            if not isinstance(string, list):
                string = list(string)
            string.sort()

        elif not isinstance(string, str):
            # default is str --> string value must also be of type str
            raise TypeError(f"field {self.field_id} is a single string (not a list of strings)")

        self.value = self.str2val(string)

    def __str__(self):
        """String value of the field."""
        string = self.str2val(self.value)
        if isinstance(string, list):
            string.sort()
            string = ",".join(string)
        return string

    @property
    def field_id(self) -> str:
        """ID suitable to use as element ``id`` in a form field."""
        return self.sep.join([self.form_id, self.name])

    def lock(self):
        self.locked = True

    def unlock(self):
        self.locked = False

    @abc.abstractmethod
    def serializable(self, mod_only: bool = True) -> SerializableType:
        """Returns a *serializable* object of this field.  With the ``mod_only``
        switch, only the difference to the default is considered: If the value
        is the same as the default, ``None`` is returned.
        """

    @abc.abstractmethod
    def apply(self, serializable: SerializableType):
        """Apply the settings to this field as generated by the method
        :py:obj:`FieldABC.serializable`.
        """

    # def parse_form(self, form: dict[str,str]):
    #     """Parse dict from the input fields of a HTML ``<form>`` element and set
    #     *this* property.
    #     """
    #     string = form.get(self.field_id, None)
    #     if string is not None:
    #         self.set(string)


class Field(FieldABC):
    """Class to map a field (string type) from a HTTP request of a submitted
    ``<form>`` element to the typed value on server side (vice versa).
    """

    def __init__(
        self,
        name: str,
        default: str,
        str2obj: MutableMapping[str, typing.Any] | Iterable[str] | typing.Callable[[str], typing.Any] = str,
        description: LazyString | str = "",
        legend: LazyString | str = "",
        ui_class: str = "",
    ):
        super().__init__(
            name=name,
            default=default,
            str2obj=str2obj,
            description=description,
            legend=legend,
            ui_class=ui_class,
        )

    # ABC methods ..

    def serializable(self, mod_only: bool = True) -> SerializableType:
        """Returns a *serializable* object of this field.  With the ``mod_only``
        switch, only the difference to the default is considered: If the value
        is the same as the default, ``None`` is returned.
        """
        string: str = self.val2str(self.value)  # type: ignore
        if mod_only and string == self.default:
            return None
        return string

    def apply(self, serializable: SerializableType):
        """Applying the settings to this field as generated by the method
        :py:obj:`Field.serializable`.
        """
        if serializable is None:
            return
        if isinstance(serializable, str):
            self.set(serializable)
        raise TypeError(f"field {self.field_id} can only process str (not '{type(serializable)}')")


class SingleChoice(Field):
    """Class suitable for the implementation of catalogs from which a (one)
    choice can be made."""

    str2obj: MutableMapping[str, typing.Any] | Iterable[str]  # type: ignore
    catalog_descr: dict[str, LazyString | str]

    def __init__(
        self,
        name: str,
        default: str,
        catalog: MutableMapping[str, typing.Any] | Iterable[str],
        description: LazyString | str = "",
        legend: LazyString | str = "",
        catalog_descr: dict[str, LazyString | str] | None = None,
        ui_class: str = "",
    ):
        self.catalog_descr = catalog_descr or {}
        super().__init__(
            name=name,
            default=default,
            str2obj=catalog,
            description=description,
            legend=legend,
            ui_class=ui_class,
        )

    @property
    def catalog(self) -> typing.Generator[tuple[str, LazyString | str, bool]]:
        """Iterator suitable to generate a list of options.  Returns a three
        digit tuple::

            ( {{value: str}}, {{description: str}}, {{selected: bool}} )

        .. code:: html

            <option value="{{value}}" {% if selected %} selected {% endif %}>
            {{description}}
            </option>

        """
        _val = self.val2str(self.value)
        for str_val in self.str2obj:
            descr = self.catalog_descr.get(str_val, lazy_gettext(str_val))
            selected = bool(str_val == _val)
            yield (str_val, descr, selected)


class Bool(SingleChoice):
    """Class suitable for the implementation on/off switches."""

    value: bool
    bool2str: dict[bool, str] = {True: "1", False: "0"}

    def __init__(
        self,
        name: str,
        default: str,
        description: LazyString | str = "",
        legend: LazyString | str = "",
        bool2str: dict[bool, str] | None = None,
        catalog_descr: dict[str, LazyString | str] | None = None,
        ui_class: str = "",
    ):
        if bool2str is not None:
            self.bool2str = bool2str

        if catalog_descr is None:
            catalog_descr = {
                self.bool2str[True]: lazy_gettext("On"),
                self.bool2str[False]: lazy_gettext("Off"),
            }
        super().__init__(
            name=name,
            default=default,
            catalog={v: k for k, v in self.bool2str.items()},
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

    value: list[typing.Any]
    str2obj: MutableMapping[str, typing.Any] | Iterable[str]  # type: ignore
    catalog_descr: dict[str, LazyString | str]

    def __init__(
        self,
        name: str,
        default: list[str],
        catalog: dict[str, typing.Any] | Sequence[typing.Any] | set[typing.Any],
        description: LazyString | str = "",
        legend: LazyString | str = "",
        catalog_descr: dict[str, LazyString | str] | None = None,
        ui_class: str = "",
    ):
        self.catalog_descr = catalog_descr or {}

        super().__init__(
            name=name,
            default=default,
            str2obj=catalog,
            description=description,
            legend=legend,
            ui_class=ui_class,
        )

    def item_id(self, item_name) -> str:
        """Returns the item ID for key (str) in the catalog.  This ID can be
        used for the ``name`` attribute of a ``<input>`` control in the
        selection catalog.

        A simple example, if name of the form is ``pref`` and the name of the
        catalog is ``categories`` and the selected item from the catalog is
        named "images" a HTML input form might looks like

        .. code:: html

          <input type="checkbox" name="form»categories»videos">
          <input type="checkbox" name="form»categories»images" checked>
        """
        return self.sep.join([self.field_id, item_name])

    @property
    def catalog(self) -> typing.Generator[tuple[str, str, LazyString | str, bool]]:
        """Iterator suitable to generate a list of options.  Returns a three
        digit tuple::

            ( {{name: str}}, {{value: str}}, {{description: str}}, {{selected: bool}} )

        .. code:: html

          <input
              type="checkbox"
              id="{{name}}"
              name="{{name}}"
              {% if selected %} checked {% endif %}>
          <label for="{{name}}">{{value}} : {{description}}</label>

        """
        _val = [self.val2str(v) for v in self.value]

        for str_val in self.str2obj:
            name = self.item_id(str_val)
            descr = self.catalog_descr.get(str_val, lazy_gettext(str_val))
            selected = str_val in _val
            yield (name, str_val, descr, selected)

    # ABC methods ..

    def serializable(self, mod_only: bool = True) -> list[str] | None:
        """Returns a *serializable* object of this field.  With the ``mod_only``
        switch, only the difference to the default is considered: If the value
        is the same as the default, ``None`` is returned.
        """
        str_list: list = self.val2str(self.value)  # type: ignore
        if mod_only and set(str_list) == set(self.default):
            return None
        return str_list

    def apply(self, serializable: SerializableType):
        """Applying the settings to this field as generated by the method
        :py:obj:`Field.serializable`.
        """
        if serializable is None:
            return
        if isinstance(serializable, list):
            invalid_types = [type(i).__name__ for i in serializable if type(i) != str]
            TypeError(f"field {self.field_id} can only process list of str (not {','.join(invalid_types)})")
            self.set(serializable)
        raise TypeError(f"field {self.field_id} can only process list (not '{type(serializable)}')")

    # def parse_form(self, form: dict[str,str]):
    #     new_val = set()
    #     for item_name in self.str2obj:
    #         str_val = form.get(self.item_id(item_name), UNKNOWN)
    #         if str_val is not UNKNOWN:
    #             new_val.add(self.val2str(str_val))
    #     self.set(new_val)


class BoolGrp(abc.ABC):
    """Abstract base class to group :py:obj:`Bool` fields."""

    sep: str = "»"
    form_id: str = "form"

    grp_id: str
    """ID/Name of *this* group."""

    members: dict[str, Bool]
    """Fields in *this* group."""

    def __init__(self, form_id: str, grp_id: str, members: dict[str, Bool]):
        self.form_id = form_id
        self.grp_id = grp_id
        self.members = members

    @property
    def group_prefix(self):
        return self.sep.join([self.form_id, self.grp_id])

    def serializable(self, mod_only: bool = True) -> dict[str, list[str]] | list[str] | None:
        """Returns a *serializable* object of this group.

        With the ``mod_only`` switch, only the difference to the default is
        considered: If the value is the same as the default, ``None`` is
        returned.

        ``mod_only``: ``True``
           The *val* is a dictionary with two keys ..

           - "on": members that have been changed from default ``False``
           - "off": members that have been changed from default ``True``

        ``mod_only``: ``False``
           The *val* is a list of members set to True, all other members in the
           group are False.
        """
        if not mod_only:
            return [m.name for m in self.members.values() if m.value]

        on_off = {"on": [], "off": []}
        for name, member in self.members.items():
            if member.val2str(member.value) == member.default:
                continue
            if member.value:
                on_off["on"].append(name)
            else:
                on_off["off"].append(name)
        if not on_off["off"]:
            del on_off["off"]
        if not on_off["on"]:
            del on_off["on"]

        return on_off or None

    def apply(self, serializable: dict[str, list[str]] | list[str] | None):
        """Apply the settings to this field as generated by the method
        :py:obj:`BoolGrp.serializable`.
        """
        if serializable is None:
            return
        if isinstance(serializable, list):
            for name, member in self.members.items():
                if name in serializable:
                    member.value = True
                else:
                    member.value = False
        elif isinstance(serializable, dict):
            for name in serializable.get("on", []):
                self.members[name].value = True
            for name in serializable.get("on", []):
                self.members[name].value = False
        raise TypeError(f"bool group {self.grp_id} can only process list or dict (not '{type(serializable)}')")

    # def parse_form(self, form: dict[str,str]):
    #     """Parse dict from the input fields of a HTML ``<form>`` element and set
    #     the members of *this* group to values of the fields with prefix
    #     :py:obj:`Preference.grp_prefix`.
    #     """
    #     for field_id, field_val in form.items():
    #         if not field_id.startswith(self.group_prefix):
    #             continue
    #         self.members[field_id].set(field_val)


@dataclasses.dataclass
class FieldCollection:
    """Typedefinition for a collection of fields (:py:obj:`FieldABC` |
    :py:obj:`BoolGrp`)."""

    def __post_init__(self):

        # We need to "lazy evaluate" this mapping (see self.__getitem___): the
        # fields are not “frozen” and can be changed in the initialization phase
        # of the surrounding Form object and its Form.form_id value on wich the
        # field_id depends on.

        self.__form_id2field: dict[str, FieldABC] | None = None

    def __iter__(self):

        for f in dataclasses.fields(self):
            field: FieldABC | BoolGrp = getattr(self, f.name)
            yield field

    def __getitem__(self, field_id: str) -> FieldABC:

        if self.__form_id2field is not None:
            return self.__form_id2field[field_id]

        _fields: list[tuple[str, FieldABC]] = []
        for field in self:
            if isinstance(field, BoolGrp):
                for m in field.members.values():
                    _fields.append((m.field_id, m))
            else:
                _fields.append((field.field_id, field))

        self.__form_id2field = {}
        id_list = []
        for f_id, field in _fields:
            if f_id in id_list:
                raise ValueError(f"duplicate use of field_id {f_id}")
            self.__form_id2field[f_id] = field
        return self.__form_id2field[field_id]


class Form:
    """A component to implement forms."""

    form_id: str = "form"
    """The ``form_id`` is used in ``id`` and ``name`` attributes in the
    corresponding HTML elements (e.g. form_, fieldset_, ..) and should therefore
    not have any special characters.

    _form: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/form#name
    _fieldset: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/fieldset#form
    """

    sep: str = "»"
    """Separator used to generate IDs for the form and its fields."""

    def __init__(self, form_id: str, fields: FieldCollection, cookie_name: str | None):
        self.form_id = form_id
        self.fields = fields
        self.cookie_name = cookie_name
        for field in self.fields:
            field.form_id = self.form_id
            field.sep = self.sep

    def save_cookie(self, resp: SXNG_Response, max_age: int = COOKIE_MAX_AGE):
        """Save field settings in a cookie of name :py:obj:`Form.cookie_name`"""
        if not self.cookie_name:
            raise ValueError(f"Form {self.form_id} does not have a cooky name.")
        resp.set_cookie(self.cookie_name, self.get_b64encode(mod_only=True), max_age=max_age)

    def parse_cookies(self, req: SXNG_Request):
        """Read cookie of name :py:obj:`Form.cookie_name` from domain cookies
        and load the field settings from this cookie.
        """
        if not self.cookie_name:
            raise ValueError(f"Form {self.form_id} does not have a cooky name.")
        cookie = req.cookies.get(self.cookie_name)
        if cookie:
            self.load_b64encode(cookie)

    def serializable(self, mod_only: bool = True) -> dict | None:
        """Returns a *serializable* object of this collection of fields"""
        ret_val = {}
        for field in self.fields:
            s = field.serializable(mod_only=mod_only)
            if s is not None:
                if isinstance(field, BoolGrp):
                    ret_val[field.grp_id] = s
                else:
                    ret_val[field.field_id] = s
        return ret_val or None

    def apply(self, serializable: dict | None):
        """Apply the settings to the fields of this collection as generated by
        the method :py:obj:`FieldCollection.serializable`.
        """
        if serializable is None:
            return
        for name, value in serializable.items():
            field: FieldABC | BoolGrp = getattr(self.fields, name)
            field.apply(value)

    def get_JSON(self, mod_only=True) -> str:
        """Returns a JSON string of this collection."""
        return json.dumps(self.serializable(mod_only=mod_only))

    def load_JSON(self, json_str: str):
        """Load settings from a JSON string."""
        self.apply(json.loads(json_str))

    def get_b64encode(self, mod_only=True) -> str:
        """A *url-safe* Base64 encoded string representing the settings of this
        collection.  It is the JSON representation that has been compressed and
        can be used as a parameter in URLs
        """
        data_str = self.get_JSON(mod_only=mod_only).encode()
        return urlsafe_b64encode(compress(data_str)).decode()

    def load_b64encode(self, base64_str: str):
        """Load settings from a (compressed) Base64 encoded string."""
        data_str = decompress(urlsafe_b64decode(base64_str))
        self.load_JSON(data_str.decode())

    def lock(self, field_names: list[str]):
        """Locks fields with the given names."""
        for name in field_names:
            field = getattr(self.fields, name)
            if isinstance(field, FieldABC):
                field.lock()
            else:
                raise TypeError(f"field {name} of type {type(field)} can't be locked")

    def unlock(self, field_names: list[str]):
        """Unlocks fields with the given names."""
        for name in field_names:
            field = getattr(self.fields, name)
            if isinstance(field, FieldABC):
                field.unlock()
            else:
                raise TypeError(f"field {name} of type {type(field)} can't be unlocked")

    def parse_request(self):
        """Set the field values from the form of the request."""

        for field_id, string in sxng_request.form.items():
            if not field_id.startswith(self.form_id):
                continue
            self.fields[field_id].set(string)

    # def is_locked(self, comp_name: str) -> bool:
    #     """Returns lock state True/False of the component ``comp_name``."""
    #     comp = self.components[comp_name]
    #     if isinstance(comp, BoolGrp):
    #         # there is no lock for members of BoolGrp
    #         return True
    #     return comp.locked

    # def value(self, comp_name: str) -> typing.Any:
    #     """Returns value of the component ``comp_name``."""
    #     comp = self.components[comp_name]
    #     if isinstance(comp, BoolGrp):
    #         # in case of BoolGrp return field names and their values
    #         return comp.members
    #     return comp.value

    # def str(self, comp_name: str) -> str | dict[str, str]:
    #     """Returns string value of the component ``comp_name``."""
    #     comp = self.components[comp_name]
    #     if isinstance(comp, BoolGrp):
    #         # in case of BoolGrp return field names and their values
    #         return {name: field.str for name, field in comp.members.items()}
    #     return comp.str
