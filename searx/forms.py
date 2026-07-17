# SPDX-License-Identifier: AGPL-3.0-or-later
"""Basic implementation for HTML forms (``<form>``).

For representing individual fields of a form, there is the class :obj:`Field`.
For larger groups of On/Off switches, the class :obj:`OnOffGroup` is much more
suitable.
"""

import typing as t

import abc
from collections import abc as c_abc
from functools import cached_property, wraps
from dataclasses import dataclass

import re
import urllib.parse
import msgspec

import flask
from flask_babel import LazyString  # type: ignore[reportMissingTypeStubs]
from werkzeug.datastructures import ImmutableMultiDict

COOKIE_MAX_AGE = 60 * 60 * 24 * 30 * 3  # ~three month
COOKIE_PREFIX: str = "SXNG"
FORM_PREFIX: str = "SXNG"

ValT = t.TypeVar("ValT")
"""Type variable for generic type definitions."""

KeyT = t.TypeVar("KeyT", bound=c_abc.Hashable)
"""Type variable for generic type definitions of the hashable keys of a mapping
typ."""


@t.final
class Void:
    __slots__ = ()


VOID: t.Final = Void()

ScalarType: t.TypeAlias = bool | int | float | complex | str | bytes
"""Python scalar type."""

SCALAR_TYPES: tuple[type, ...] = t.get_args(ScalarType)
"""Python's scalar types."""

FIELD_ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{1,40}$")
"""Pattern for the ID of a (HTML) field.

In order for IDs to be used in the ``id`` attribute of a HTML tag and in a
cookie name, they should consist of simple sequences of letters and, if
applicable, digits.

The characters ``-`` and ``.`` are reserved for internal purposes and are also
not suitable for CSS selectors.  The ID should not be longer than 40 characters,
as it may still be extended internally and then could cause problems with cookie
names.
"""

_P = t.ParamSpec("_P")
_R = t.TypeVar("_R")
_S = t.TypeVar("_S", "Field[t.Any]", "OnOffGroup")


def if_mutable(
    method: c_abc.Callable[t.Concatenate[_S, _P], _R],
) -> c_abc.Callable[t.Concatenate[_S, _P], _R | Void]:
    """Method decorator.  If the field is :obj:`Field.locked`, the call is
    ignored and :obj:`VOID` is returned.
    """

    @wraps(method)
    def wrapper(self: _S, *args: _P.args, **kwargs: _P.kwargs) -> _R | Void:
        if self.locked:
            return VOID
        return method(self, *args, **kwargs)

    return wrapper


BoolLiteral: t.TypeAlias = t.Literal["1", "0", "on", "off", "True", "False", "true", "false", "None", "null"]
"""Alias names for bool values."""

BOOL_MAP: dict[str, bool] = {
    "true": True,
    "false": False,
    "on": True,
    "off": False,
    "1": True,
    "0": False,
    "none": False,
    "null": False,
}
"""Map :py:obj:`BoolLiteral` to the bool values."""


class Cookie(msgspec.Struct, kw_only=True):
    """A simple structure to encode/decode a cookie."""

    data: list[str]


# Catalogs
# --------

ON_OFF: dict[str, bool] = {"on": True, "off": False}

# python >= 3.12
# type CatalogDefType[T] = (
#     c_abc.Mapping[
#         str | None,
#         T |  c_abc.Callable[[str], T],
#     ]
#     | c_abc.Mapping[
#         str,
#         T |  c_abc.Callable[[str], T],
#     ]
#     | c_abc.Sequence[
#         T | c_abc.Callable[[str], T],
#     ]
# )

# python 3.11
CatalogDefType: t.TypeAlias = (
    c_abc.Mapping[
        str | None,
        ValT | c_abc.Callable[[str], ValT],
    ]
    # The key type "str | None" is not covariant; for example, to allow a type
    # dict[str, bool], the following mapping is still required (even if it is a
    # subset of "str | None")
    | c_abc.Mapping[
        str,
        ValT | c_abc.Callable[[str], ValT],
    ]
    | c_abc.Sequence[ValT | c_abc.Callable[[str], ValT],]
)


class Catalog(t.Generic[ValT]):
    """A catalog with parameterized generic type for a form field.

    The catalog can be built from a list or a mapping (key/value pairs).  The
    keys must be strings, if a list of Python objects is passed, the string
    representation of the objects is used as the key.

    The key with the value ``None`` has a special meaning; it indicates that
    values not present in the catalog are also allowed:

    .. code:: python

        >>> cat: Catalog[int | float | Path | None] = Catalog(
        ...     {
        ...         "answer": 42,
        ...         "pi": 3.14,
        ...         None: lambda name: p if (p := Path(name)).is_dir() else None,
        ...     }
        ... )
        >>> print(repr(cat["/tmp"]) or "not a dir")
        PosixPath('/tmp')
        >>> print(repr(cat["/tmp/unknown"]) or "not a dir")
        "'not a dir'"
        >>> print(repr(cat["pi"]))
        <class 'float'>

    A catalog that accepts existing paths:

    .. code:: python

        >>> path_cat: Catalog[Path | None] = Catalog(
        ...     [lambda name: p if (p := Path(name)).is_dir() else None]
        ... )
        >>> path_cat["/tmp"]
        PosixPath('/tmp')
        >>> print(path_cat["/tmp/unknown"])
        None
    """

    __catalog: dict[str | None, ValT | c_abc.Callable[[str], ValT | None]]

    restrict: bool = True
    """Indicates whether a valid value may only be taken from the catalog, or
    whether free values are also allowed (catalog contains a key with the value
    ``None``).
    """

    def __init__(
        self,
        catalog: CatalogDefType[ValT],
    ):
        if isinstance(catalog, c_abc.Mapping):
            self.__catalog = {str(k): v for k, v in catalog.items()}
        elif isinstance(catalog, c_abc.Sequence):
            self.__catalog = {}
            for k in catalog:
                if callable(k):
                    self.__catalog[None] = k
                else:
                    self.__catalog[str(k)] = k
        else:
            raise ValueError(f"expect catalog, got: {catalog}")  # type: ignore[reportUnreachable]
        self.restrict = None in self.__catalog.keys()

    def __bool__(self):
        return bool(self.__catalog)

    def __getitem__(self, key: str) -> t.Any:  # type: ignore[reportAny]
        cat_val = self.__catalog.get(key, VOID)
        if not isinstance(cat_val, Void):
            return t.cast(ValT, cat_val)

        if not self.restrict:
            try:
                return self.__catalog[None](key)  # type: ignore[reportCallIssue]
            except (ValueError, TypeError):
                pass
        raise KeyError(f"{key} not in restricted catalog")

    def py2strlist(self, obj_list: list[t.Any]) -> list[str]:
        ret_val: list[str] = []
        for obj in obj_list:  # type: ignore[reportAny]
            obj_type = type(obj)  # pyright: ignore[reportAny, reportUnknownVariableType]
            for cat_key, cat_val in self.__catalog.items():
                if cat_key is None:
                    # if None is a key in the catalog, it maps to a callable
                    continue
                # A simple agreement on values ​​is not enough, for
                # instance:
                #   int(1) == float(1.0)   --> True
                #   True == int(1)         --> True
                #   complex(0, 0j) == 0.0  --> True
                # The type also needs to be compared!
                if isinstance(cat_val, obj_type) and obj == cat_val:
                    ret_val.append(cat_key)
        return ret_val

    def strlist2py(self, str_list: list[str]) -> list[t.Any]:
        return [self[k] for k in str_list]

    @t.final
    @cached_property
    def options(self) -> list[str]:
        """Options that the catalog offers."""
        return [k for k in self.__catalog.keys() if isinstance(k, str)]


# Field Listeners
# ---------------

MsgT = t.TypeVar("MsgT", bound="Msg[t.Any]")

FieldType: t.TypeAlias = "Field[ValT] | OnOffGroup"
Listener: t.TypeAlias = "t.Callable[[MsgT], None]"
MSG_TYPES: "set[type[Msg[t.Any]]]" = set()


@dataclass(frozen=True)
class Msg(abc.ABC, t.Generic[ValT]):
    field: "FieldType[ValT]"

    def __init_subclass__(cls, **kwargs: t.Any):  # type: ignore[reportAny]
        MSG_TYPES.add(cls)
        super().__init_subclass__(**kwargs)


class MsgBus:

    listeners: "dict[type[Msg[t.Any]], set[Listener[t.Any]]]"

    class msg:
        @dataclass(frozen=True)
        class updated(Msg[ValT], t.Generic[ValT]):
            """Field has been updated."""

            old_val: ValT

        # @dataclass(frozen=True)
        # class parsed(Msg[ValT], t.Generic[ValT]):
        #     """Field has been updated."""

    def __init__(self) -> None:
        self.listeners = {}

    def listen(self, msg_cls: type[MsgT], listener: "Listener[MsgT]") -> None:
        self.listeners.setdefault(msg_cls, set()).add(listener)

    def unlisten(self, listener: "Listener[MsgT]", msg_type: "type[Msg[t.Any]] | None") -> None:
        if msg_type is None:
            for s in self.listeners.values():
                s.discard(listener)
            return
        if s := self.listeners.get(msg_type):
            s.discard(listener)

    def publish(self, msg: Msg[t.Any]):
        for h in self.listeners[type(msg)]:
            h(msg)


# Field
# -----


class FieldDef(t.TypedDict, t.Generic[ValT]):
    """Dictionary type, structured similar to :py:obj:`Field` constructor and
    used in factory, class method: :obj:`Field.from_def`."""

    id: str
    default: c_abc.Sequence[ValT] | ValT

    catalog: t.NotRequired[CatalogDefType[ValT]]
    locked: t.NotRequired[bool]
    l10n_descr: t.NotRequired[LazyString | str]


class Field(MsgBus, t.Generic[ValT]):
    """Class for implementing fields for forms

    A field has the following representations

    - A field in a HTML form: an attribute/value pair that is exchanged via
      strings between client and server (:py:obj:`Field.upd_from_form`).

    - A cookie in the domain cookies: an attribute/value pair that is exchanged
      via strings, the pair is set by the server on the client and the client
      sends the cookie with every request (:py:obj:`Field.upd_from_cookies`).

    Furthermore, there is also the Python internal representation
    :py:obj:`Field.val`, or in the case of multiple selection
    :py:obj:`Field.values`.

    The representation requires a conversion from the Python type to a string
    and vice versa.  Python's builtin scalar types are supported, for more
    complex types a catalog can be used that maps a string to an object in
    Python.

    A field must have a default value; the default value is needed, among other
    things, to implicitly determine the data type of the field.  The
    :py:obj:`SCALAR_TYPES` are supported; if a list is passed in the
    constructor, then it must contain at least one value for type determination.

    Passing a list in the constructor sets the flag :py:obj:`Field.multiple`,
    which indicates that this field is suitable for multiple selections
    """

    id: str
    """ID of this field, see :py:obj:`FIELD_ID_PATTERN`"""

    catalog: Catalog[ValT]
    """Access to the :obj:`Catalog` of this field."""

    locked: bool = False
    """Field is locked and cannot be adjusted by the user."""

    l10n_descr: LazyString | str = ""
    """Localized description of the field."""

    multiple: bool
    """Indicates whether this field allows multiple selection or not.

    Multiple selection is available if the `default` in the constructor is a
    list (:py:ob:`collections.abc.Sequence`).

    Examples: checkbox_ and  `radio button`_

    .. _checkbox:
       https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/checkbox#handling_multiple_checkboxes
    .. _radio button:
       https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/radio
        """

    __values: list[ValT]
    __py_type: type

    def __init__(
        self,
        id: str,
        default: c_abc.Sequence[ValT] | ValT,
        catalog: Catalog[ValT] | CatalogDefType[ValT] | None = None,
        locked: bool = False,
        l10n_descr: LazyString | str = "",
    ):
        if not FIELD_ID_PATTERN.fullmatch(id):
            raise ValueError(f"field ID {id} contains invalid characters")
        super().__init__()

        self.id = id
        self.l10n_descr = l10n_descr

        if isinstance(default, c_abc.Sequence):
            self.__multiple = True
        else:
            self.__multiple = False
            default = [default]

        obj = next(iter(default), None)  # type: ignore[reportUnknownArgumentType]
        if obj is None:
            raise TypeError(f"Field.__init__() missing required default value: {default} ")
        self.__py_type = type(obj)

        if isinstance(catalog, Catalog):
            self.catalog = catalog
        else:
            self.catalog = Catalog(catalog=catalog or {})

        self.locked = False
        self.upd(default)  # pyright: ignore[reportUnknownArgumentType]
        self.locked = locked

    @classmethod
    def from_def(cls, field_def: FieldDef[ValT]) -> t.Self:
        return cls(
            id=field_def["id"],
            locked=field_def.get("locked", False),
            default=field_def["default"],
            catalog=t.cast(Catalog[ValT] | None, field_def.get("locked")),
        )

    # Python representation ..

    @property
    def val(self) -> ValT:
        """The python internal value of this field."""
        return self.__values[0]

    @property
    def values(self) -> list[ValT]:
        """The python internal values of this field."""
        return self.__values

    @t.final
    @if_mutable
    def upd(self, new_val: ValT | c_abc.Sequence[ValT]) -> None:
        """Setter method to set the *internal* (python) value of this field.

        If the field is :obj:`Field.locked`, the call is ignored and :obj:`VOID`
        is returned.
        """
        old_val = self.values
        if isinstance(new_val, c_abc.Sequence):
            self.__values = new_val  # type: ignore[reportAttributeAccessIssue]
        else:
            self.__values = [new_val]

        self.publish(self.msg.updated(field=self, old_val=old_val))

    # form (HTML) representation ..

    @cached_property
    def form_name(self) -> str:
        """The field name of this field in a HTML form."""
        return f"{FORM_PREFIX}.{self.id}"

    @property
    def form_value(self) -> str:
        """The corresponding string value for the python internal value of this
        field."""
        return self.py2strlist([self.val])[0]

    @property
    def form_values(self) -> list[str]:
        """A list of corresponding string values for the python internal values
        of this field."""
        return self.py2strlist(self.values)

    @if_mutable
    def upd_from_form(self, form: ImmutableMultiDict[str, str]) -> None:
        """If :obj:`Field.field_name` is present in the form data, the python
        value of this field will be overwritten by the value from the form.

        If the field is :obj:`Field.locked`, the call is ignored and :obj:`VOID`
        is returned.
        """
        raw: list[str] | None = form.getlist(self.form_name)
        if not raw:
            return
        new_val = self.strlist2py(raw)
        self.upd(new_val)

    def py2strlist(self, obj_list: list[ValT]) -> list[str]:
        """Converts Python objects to strings.

        If a catalog exists, the objects from the catalog are used to find the
        corresponding string value.  If there is no matching entry in the
        catalog, this python value is ignored.
        """
        if not self.catalog:
            return [str(v) for v in obj_list]
        return self.catalog.py2strlist(obj_list)

    def strlist2py(self, str_list: list[str]) -> list[ValT]:
        """Convert the strings from the list into the Python objects of this
        field.

        The scalar types are built from the strings of the form; if a ValueError
        exception occurs in the process, the string is ignored.

        If a catalog exists, the objects from the catalog are used as the
        corresponding Python value.  If there is no matching entry for a string
        in the catalog, this string is ignored as well.
        """
        if self.catalog:
            return self.catalog.strlist2py(str_list)
        ret_val: list[ValT] = []
        for opt_str in str_list:
            try:
                ret_val.append(self.__py_type(opt_str))  # type: ignore[reportCallIssue]
            except (ValueError, TypeError):
                pass
        return ret_val

    # cookie representation ..

    @property
    def cookie_name(self) -> str:
        """The cookie name of this field in the domain cookies."""
        return f"{COOKIE_PREFIX}.{self.id}"

    @property
    def cookie_value(self) -> str:
        """The value of the cookie, a URL-quoted JSON string."""
        return self.strlist2cookie(self.py2strlist(self.values))

    def send_cookie(self, resp: flask.Response):
        """Adds the cookie of this field to the HTTP response."""
        resp.set_cookie(self.cookie_name, self.cookie_value, max_age=COOKIE_MAX_AGE)

    @if_mutable
    def upd_from_cookies(self, cookies: dict[str, str]):
        """If present in the cookies, the value of this field will be
        updated by the value from the cookie.

        If the field is :obj:`Field.locked`, the call is ignored and :obj:`VOID`
        is returned.
        """
        raw_str: str | None = cookies.get(self.cookie_name)
        if raw_str is None:
            return
        new_val = self.strlist2py(self.cookie2strlist(raw_str))
        self.upd(new_val)

    def strlist2cookie(self, str_list: list[str]) -> str:
        cookie_obj = Cookie(data=str_list)
        json_str = msgspec.json.encode(cookie_obj).decode()
        raw_str = urllib.parse.quote(json_str)
        return raw_str

    def cookie2strlist(self, raw_str: str) -> list[str]:
        json_str = urllib.parse.unquote(raw_str)
        cookie_obj = msgspec.json.decode(json_str, type=Cookie)
        return cookie_obj.data


class OnOffDict(t.TypedDict):
    """Dictionary type, structured similar to :py:obj:`OnOffStruct`."""

    # pylint: disable=invalid-name

    on: t.NotRequired[dict[str, str]]
    off: t.NotRequired[dict[str, str]]


class OnOffStruct(msgspec.Struct, kw_only=True):
    """Auxiliary construct for managing switches that are combined into a group
    (:py:obj:`OnOffGroup`).

    A switch has a name and it is used in an (optinal) context.  Both together,
    the name and the context, form an entity.

    For intance; an engine in SearXNG can be active in one category but inactive
    in another category.  The name of the engine is the ``name`` of the switch,
    and the category determines the context (``ctx``) in which the engine should
    be active or not (``on`` / ``off``).

    Each entity in the group can only ever be in one state (*on* ``XOR`` *off*);
    only then is the group valid (:py:obj:`.is_valid`).
    """

    # pylint: disable=invalid-name

    # { <name>: <ctx> , ... }
    on: dict[str, str] = msgspec.field(default_factory=dict)
    off: dict[str, str] = msgspec.field(default_factory=dict)

    def __post_init__(self):
        if not self.is_valid:
            intersect = set(self.on.items()) & set(self.off.items())
            raise ValueError(f"State of entity can't be *on* and *off* at the same time: {intersect}")

    @property
    def is_valid(self) -> bool:
        """An entity of ``(name, ctx)`` can only exist once (the state is
        disjoint); it cannot be *on* and *off* at the same time.
        """
        on = set(self.on.items())
        off = set(self.off.items())
        return on.isdisjoint(off)

    def enable(self, name: str, ctx: str = ""):
        self.on[name] = ctx
        if self.off.get(name) == ctx:
            del self.off[name]

    def disable(self, name: str, ctx: str = ""):
        self.off[name] = ctx
        if self.on.get(name) == ctx:
            del self.on[name]

    def update(self, other: "OnOffStruct"):
        for name, ctx in other.on.items():
            self.enable(name, ctx)
        for name, ctx in other.off.items():
            self.disable(name, ctx)

    def diff(self, other: "OnOffStruct") -> "OnOffStruct":
        """Returns a new instance with the difference ("on" vs. "off") of the
        intersection entities ``(name, ctx)`` of *self* and *other*.

        In the returned object are the entities that have a different state in
        *self* than in *other* and the entities that are in *other* but not in
        *self*.
        """
        new = OnOffStruct()
        for item_name, ctx in other.on.items():
            if not self.on.get(item_name) == ctx:
                new.on[item_name] = ctx
        for item_name, ctx in other.off.items():
            if not self.off.get(item_name) == ctx:
                new.off[item_name] = ctx
        return new


class OnOffGroup(MsgBus):
    """Class for the efficient management of entire groups of switches.

    Switches with the group prefix :obj:`OnOffGroup.id` in the ID are
    grouped together.

    A special feature of SearXNG is that the preferences are not stored on the
    server; they are stored in as cookies on the client and sent to the server
    with each request.  With more than two hundred search engines that can have
    different on/off states in 10 or more different categories, this would
    quickly result in thousands of fields being stored in cookies.

    As is well known, the number and size of cookies are strongly limited by the
    components involved in the exchange, and it should also not be forgotten
    that the cookies must be transferred with every request as a base load.
    Since all cookies of a domain are always be sent, excessive cookies can also
    have side effects on other applications that are operated under the same
    domain.

    The On/Off group tries to mitigate this load, it is based on two
    assumptions:

    1. There is a default configuration
    2. A user will only change a few switches, and it is sufficient to transmit
       this difference from the defaults.
    """

    cfg: OnOffStruct
    """Default settings that serve as base for the diff."""

    id: str
    """Prefix of field IDs in this group, see :py:obj:`FIELD_ID_PATTERN`"""

    locked: bool
    """Group of fields is locked and cannot be adjusted by the user."""

    __values: OnOffStruct

    def __init__(
        self,
        grp_id: str,
        locked: bool,
        cfg: OnOffStruct | OnOffDict,
    ):

        if not FIELD_ID_PATTERN.fullmatch(grp_id):
            raise ValueError(f"group name {grp_id} contains invalid characters")
        super().__init__()
        self.id = grp_id

        if isinstance(cfg, OnOffStruct):
            self.cfg = cfg
        else:
            self.cfg = OnOffStruct(on=cfg.get("on", {}), off=cfg.get("off", {}))

        # a deep-copy is needed (incl. type validation)
        value = msgspec.msgpack.decode(
            msgspec.msgpack.encode(self.cfg),
            type=OnOffStruct,
        )

        self.locked = False
        self.upd(value)
        self.locked = locked

    # Python representation ..

    @property
    def val(self) -> OnOffStruct:
        """The python internal data structure of this group of fields."""
        return self.__values

    @t.final
    @if_mutable
    def upd(self, new_val: OnOffStruct) -> None:
        """Setter method to set the *internal* (python) value of this group of
        fields.

        If the group is :obj:`OnOffStruct.locked`, the call is ignored and
        :obj:`VOID` is returned.
        """
        old_val = self.__values
        self.__values = new_val
        self.publish(self.msg.updated(field=self, old_val=old_val))

    # HTML form representation ..

    @cached_property
    def form_name(self) -> str:
        """The prefix of the field names of this group in a HTML form."""
        return f"{FORM_PREFIX}.{self.id}."

    @if_mutable
    def upd_from_form(self, form: ImmutableMultiDict[str, str]) -> None:
        """Fields with the group prefix :obj:`OnOffGroup.id` in the ID are
        evaluated.

        If the group is :obj:`OnOffGroup.locked`, the call is ignored and
        :obj:`VOID` is returned.

        Values of fields are sent to the server via an HTML form.  HTML checkbox
        (``input``) example::

        <input id="{OnOffGroup.id}.{field_name}.{ctx}" type="checkbox">

        .. attention::

           `Checkable item`_: In the case of checkable items, their values are
           sent only if they are checked.  If they are not checked, nothing is
           sent, not even their name. If they are checked but have no value, the
           name is sent with a value of ``on``.

        .. _Checkable item:
           https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Forms/Basic_native_form_controls#checkable_items_checkboxes_and_radio_buttons
        """

        on_fields: set[tuple[str, str]] = set()
        pos = len(self.form_name)
        new_val = msgspec.convert(msgspec.to_builtins(self.cfg), type=OnOffStruct)

        for fqn, field_val in form.items():
            if not fqn.startswith(self.form_name):
                continue
            item_name, ctx = (fqn[pos:].split(".", 1) + ["", ""])[:2]
            if not item_name:
                continue

            if field_val == "on":
                new_val.enable(item_name, ctx)
                on_fields.add((item_name, ctx))
            else:
                raise RuntimeError(f"HTML form, can't process value '{field_val}' from field '{fqn}'.")

        # process un-checked fields (off: nothing is send from web client)
        grp_fields = set(self.cfg.on.items()) | set(self.cfg.on.items())
        for field_name, ctx in grp_fields.difference(on_fields):
            new_val.disable(name=field_name, ctx=ctx)

    # cookie representation ..

    @property
    def cookie_name(self) -> str:
        """The cookie name of this field in the domain cookies."""
        return f"{COOKIE_PREFIX}.{self.id}"

    @property
    def cookie_value(self) -> str:
        """The value of the cookie, a URL-quoted JSON string.

        Only the differences from the defaults are returned, this must also be
        taken into account when loading the cookie.
        """
        diff_obj = self.cfg.diff(self.cfg)
        json_str = msgspec.json.encode(diff_obj).decode()
        raw_str = urllib.parse.quote(json_str)
        return raw_str

    def send_cookie(self, resp: flask.Response):
        """Adds the cookie of this field to the HTTP response."""
        resp.set_cookie(self.cookie_name, self.cookie_value, max_age=COOKIE_MAX_AGE)

    def upd_from_cookies(self, cookies: dict[str, str]):
        """If cookie :obj:`OnOffGroup.cookie_name` is present in the cookies,
        evaluate its diff to update the switches in this group.

        The entire group of fields in this group is being recreated and set as a
        new value.  The new object corresponds to the defaults, which are
        updated with the values from the cookie (the diff is applied).
        """
        raw_str: str | None = cookies.get(self.cookie_name)
        if raw_str is None:
            return

        json_str = urllib.parse.unquote(raw_str)
        diff_obj = msgspec.json.decode(json_str, type=OnOffStruct)

        new_val = msgspec.convert(msgspec.to_builtins(self.cfg), type=OnOffStruct)
        new_val.update(diff_obj)
        self.upd(new_val)
