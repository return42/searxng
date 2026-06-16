# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=too-few-public-methods,missing-module-docstring

__all__ = ["Plugin", "PluginInfo", "PluginCfg", "Storage", "StorageCfg", "StoragePlgCfg"]

import typing as t
from collections.abc import Generator
import dataclasses

import abc
import importlib
import inspect
import logging
import re

import msgspec


from searx.extended_types import SXNG_Request

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.result_types import Result, EngineResults, LegacyResult  # pyright: ignore[reportPrivateLocalImportUsage]
    import flask

log: logging.Logger = logging.getLogger("searx.plugins")

ID_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
"""In order for IDs to be used in forms, they should consist of simple sequences
of letters and, if applicable, digits."""

# Configuration of a Plugin
# -------------------------

class StoragePlgCfg(msgspec.Struct):
    """A plugin configuration in the list of configured Plugins.

.. code:: yaml

   plugins:                       # <-- StorageCfg
     # ...
     mypackage.mymodule.MyPlugin: # <-- StoragePlgCfg
       active: true
       cfg:                       # <-- PluginCfg
         option_a: 42
         option_b:
            - "foo"
            - "bar"
    """

    active: bool = True
    """Plugin is "on" by default and the user can *opt-out* in the preferences
    :py:obj:`PluginPref.active`."""

    cfg: dict[str, t.Any] = msgspec.field(default_factory=dict)


class PluginCfg(msgspec.Struct):
    """Base class for all plugin configurations."""

PluginCfgType = t.TypeVar("PluginCfgType", bound=PluginCfg)

# Plugin instances at runtime
# ---------------------------

@dataclasses.dataclass
class PluginInfo:
    """Object that holds information about a *plugin*, these infos are shown to
    the user in the Preferences menu.

    To be able to translate the information into other languages, the text must
    be written in English and translated with :py:obj:`flask_babel.gettext`.
    """

    id: str
    """The ID-selector in HTML/CSS `#<id>`."""

    name: str
    """Name of the *plugin*."""

    description: str
    """Short description of the *answerer*."""

    preference_section: t.Literal["general", "ui", "privacy", "query"] | None = "general"
    """Section (tab/group) in the preferences where this plugin is shown to the
    user.

    The value ``query`` is reserved for plugins that are activated via a
    *keyword* as part of a search query, see:

    - :py:obj:`PluginInfo.examples`
    - :py:obj:`Plugin.keywords`

    Those plugins are shown in the preferences in tab *Special Queries*.
    """

    examples: list[str] = dataclasses.field(default_factory=list)
    """List of short examples of the usage / of query terms."""

    keywords: list[str] = dataclasses.field(default_factory=list)
    """See :py:obj:`Plugin.keywords`"""


class Plugin(abc.ABC, t.Generic[PluginCfgType]):
    """Abstract base class of all Plugins."""

    id: str = ""
    """The ID (suffix) in the HTML form."""

    active: bool
    """Plugin is enabled/disabled by default (:py:obj:`PluginCfg.active`)."""

    keywords: list[str] = []
    """Keywords in the search query that activate the plugin.  The *keyword* is
    the first word in a search query.  If a plugin should be executed regardless
    of the search query, the list of keywords should be empty (which is also the
    default in the base class for Plugins)."""

    info: PluginInfo
    """Information about the *plugin*, see :py:obj:`PluginInfo`."""

    cfg: PluginCfgType
    """Configuration (setup) of the *plugin*, see :py:obj:`PluginSetup`."""

    cfg_cls: type[PluginCfg] = PluginCfg
    #PrefType: type[PluginPrefs] = PluginPrefs
    #"""Data type for the user settings (aka preferences)."""

    log: logging.Logger
    """A logger object, is automatically initialized when calling the
    constructor (if not already set in the subclass)."""

    fqn: str

    def __init__(self, storage_plg: StoragePlgCfg) -> None:
        if not self.id:
            raise NotImplementedError(f"plugin {self} is missing attribute 'id'")
        if not ID_PATTERN.fullmatch(self.id):
            raise ValueError(f"plugin ID {self.id} contains invalid character (use lowercase ASCII)")
        if not getattr(self, "log", None):
            pkg_name = inspect.getmodule(self.__class__).__package__  # pyright: ignore[reportOptionalMemberAccess]
            self.log = logging.getLogger(f"{pkg_name}.{self.id}")

        self.fqn = self.__class__.__mro__[0].__module__
        self.cfg = self.cfg_cls(**storage_plg.cfg)
        self.active = storage_plg.active

    def __hash__(self) -> int:
        """The hash value is used in :py:obj:`set`, for example, when an object
        is added to the set.  The hash value is also used in other contexts,
        e.g. when checking for equality to identify identical plugins from
        different sources (name collisions)."""

        return id(self)

    def __eq__(self, other: t.Any):  # pyright: ignore[reportAny]
        """py:obj:`Plugin` objects are equal if the hash values of the two
        objects are equal."""

        return hash(self) == hash(other)  # pyright: ignore[reportAny]

    # pylint: disable=unused-argument
    def init(self, app: "flask.Flask") -> bool:  # pyright: ignore[reportUnusedParameter]
        """Initialization of the plugin, the return value decides whether this
        plugin is active or not.  Initialization only takes place once, at the
        time the WEB application is set up.  The base method always returns
        ``True``, the method can be overwritten in the inheritances,

        - ``True`` plugin is active
        - ``False`` plugin is inactive
        """
        return True

    def pre_search(
        self, request: SXNG_Request, search: "SearchWithPlugins"  # pyright: ignore[reportUnusedParameter]
    ) -> bool:
        """Runs BEFORE the search request and returns a boolean:

        - ``True`` to continue the search
        - ``False`` to stop the search
        """
        return True

    def on_result(
        self,
        request: SXNG_Request,  # pyright: ignore[reportUnusedParameter]
        search: "SearchWithPlugins",  # pyright: ignore[reportUnusedParameter]
        result: "Result",  # pyright: ignore[reportUnusedParameter]
    ) -> bool:
        """Runs for each result of each engine and returns a boolean:

        - ``True`` to keep the result
        - ``False`` to remove the result from the result list

        The ``result`` can be modified to the needs.

        .. hint::

           If :py:obj:`Result.url <searx.result_types._base.Result.url>` is modified,
           :py:obj:`Result.parsed_url <searx.result_types._base.Result.parsed_url>` must
           be changed accordingly:

           .. code:: python

              result["parsed_url"] = urlparse(result["url"])
        """
        return True

    def post_search(
        self, request: SXNG_Request, search: "SearchWithPlugins"  # pyright: ignore[reportUnusedParameter]
    ) -> "None | list[Result | LegacyResult] | EngineResults":
        """Runs AFTER the search request.  Can return a list of
        :py:obj:`Result <searx.result_types._base.Result>` objects to be added to the
        final result list."""
        return




StorageCfg = dict[str, StoragePlgCfg]


class Storage:
    """A storage for managing the *plugins* of SearXNG."""

    @property
    def plugin_list(self) -> set[Plugin[PluginCfg]]:
        """The list of :py:obj:`Plugins` in this storage."""
        return set(self._by_id.values())

    def __init__(self):
        self._by_id: dict[str, Plugin[PluginCfg]] = {}

    def __iter__(self) -> Generator[Plugin[PluginCfg]]:
        yield from self._by_id.values()

    def __len__(self):
        return len(self._by_id)

    def get(self, id: str) -> Plugin[PluginCfg] | None:
        return self._by_id.get(id, None)

    @property
    def info(self) -> list[PluginInfo]:
        return [p.info for p in self._by_id.values()]

    def load_settings(self, cfg: StorageCfg):
        """Load plugins configured in SearXNG's settings :ref:`settings
        plugins`."""

        plg_cfg: StoragePlgCfg
        for fqn, plg_cfg in cfg.items():
            cls: type[Plugin[PluginCfg]] | None = None
            mod_name, cls_name = fqn.rsplit(".", 1)
            try:
                mod = importlib.import_module(mod_name)
                cls = getattr(mod, cls_name, None)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.exception(exc)

            if cls is None:
                msg = f"plugin {fqn} is not implemented"
                raise ValueError(msg)
            plg: Plugin[PluginCfg] = cls(plg_cfg)

            import pdb
            pdb.set_trace()
            self.register(plg)

    def register(self, plugin: Plugin[PluginCfg]):
        """Register a :py:obj:`Plugin`.  In case of name collision (if two
        plugins have same ID) a :py:obj:`KeyError` exception is raised.
        """
        if self.get(plugin.id):
            msg = f"name collision '{plugin.id}'"
            plugin.log.critical(msg)
            raise KeyError(msg)
        self._by_id[plugin.id] = plugin
        self.plugin_list.add(plugin)
        plugin.log.debug("plugin has been loaded")

    def init(self, app: "flask.Flask") -> None:
        """Calls the method :py:obj:`Plugin.init` of each plugin in this
        storage.  Depending on its return value, the plugin is removed from
        *this* storage or not."""

        for plg in self.plugin_list.copy():
            if not plg.init(app):
                self.plugin_list.remove(plg)

    def pre_search(self, request: SXNG_Request, search: "SearchWithPlugins") -> bool:

        ret = True
        for plugin in [p for p in self.plugin_list if p.id in search.user_plugins]:
            try:
                ret = bool(plugin.pre_search(request=request, search=search))
            except Exception:  # pylint: disable=broad-except
                plugin.log.exception("Exception while calling pre_search")
                continue
            if not ret:
                # skip this search on the first False from a plugin
                break
        return ret

    def on_result(self, request: SXNG_Request, search: "SearchWithPlugins", result: "Result") -> bool:

        ret = True
        for plugin in [p for p in self.plugin_list if p.id in search.user_plugins]:
            try:
                ret = bool(plugin.on_result(request=request, search=search, result=result))
            except Exception:  # pylint: disable=broad-except
                plugin.log.exception("Exception while calling on_result")
                continue
            if not ret:
                # ignore this result item on the first False from a plugin
                break

        return ret

    def post_search(self, request: SXNG_Request, search: "SearchWithPlugins") -> None:
        """Extend :py:obj:`search.result_container
        <searx.results.ResultContainer`> with result items from plugins listed
        in :py:obj:`search.user_plugins <SearchWithPlugins.user_plugins>`.
        """

        keyword = None
        for keyword in search.search_query.query.split():
            if keyword:
                break

        for plugin in [p for p in self.plugin_list if p.id in search.user_plugins]:

            if plugin.keywords:
                # plugin with keywords: skip plugin if no keyword match
                if keyword and keyword not in plugin.keywords:
                    continue
            try:
                results = plugin.post_search(request=request, search=search) or []
            except Exception:  # pylint: disable=broad-except
                plugin.log.exception("Exception while calling post_search")
                continue

            # In case of *plugins* prefix ``plugin:`` is set, see searx.result_types.Result
            search.result_container.extend(f"plugin: {plugin.id}", results)















# Prefernces of a Plugin
# ----------------------

# class Catalog(t.Generic[KeyType, ValueType]):
#     """Base class for catalogs that can be passed in the preferences."""

#     def __init__(self, records: Mapping[KeyType, ValueType]):
#         self._records: Mapping[KeyType, ValueType] = records

#     def __getitem__(self, key: KeyType) -> ValueType:
#         return self._records[key]

#     def get_value(self, name: KeyType) -> ValueType | None:
#         """Get python value for catalog item of `name`"""
#         return self._records.get(name)

#     def get_name(self, value: ValueType) -> KeyType:
#         for name, py_val in self._records.items():
#             if py_val == value:
#                 return name
#         raise KeyError(value)


# class PrefCatalog(t.Generic[PluginType, CatalogType]):
#     """A preference item based on a catalog."""

#     def __init__(self, plg: Plugin, catalog: CatalogType):

#         self.plg: Plugin = plg
#         self.catalog: CatalogType = catalog

#     def serialize(self) -> PrefDataType:
#         data: PrefDataType = PrefDataType()

#         # If Plugin.active does not match the default, the value is added to the
#         # preferences; otherwise, this is not necessary.
#         if self.plg.active != self.plg.cfg.active:
#             pref_data.active = BoolCatalog.serialize(self.plg.active)

#         return PrefDataStruct(plugins={self.plg.id: pref_data})





# OnOffLiteral = t.Literal["on", "off"]
# OnOffCatalog: Catalog[OnOffLiteral, bool] = Catalog({"on": True, "off": False})
# # OnOffPref = PrefCatalog(plg, OnOffCatalog)






# class PrefDataStruct(msgspec.Struct):
#     """A mapping table that references the preference settings (data structures)
#     for a plugin by its name."""
#     plugins: dict[str, PrefDataType] = {}





# class PrefType:
#     catalog: t.Any = None


# class PrefTypeBool(PrefType):

#     catalog: Catalog[BoolLiterals, bool] = Catalog({"on": True, "off": False})

#     def __init__(field_id: str):


# class PrefDataType(msgspec.Struct):
#     """Base class of all types (data structures) for the configuration (setup)
#     of the preferences."""

#     active: BoolLiterals | None = None

#     @classmethod
#     def serialize(cls, plg: "Plugin[PluginType]"):
#         field_dict = {}




#         pref_data: PrefDataType = cls()
#         # If Plugin.active does not match the default, the value is added to the
#         # preferences; otherwise, this is not necessary.
#         if plg.active != plg.cfg.active:
#             pref_data.active = BoolCatalog.serialize(plg.active)

#         return PrefDataStruct(plugins={plg.id: pref_data})

#     @classmethod
#     def deserialize(cls, plg: "Plugin[PluginType]", prefs: PrefDataStruct):
#         plg_prefs: PrefDataType | TVGuardType = prefs.plugins.get(plg.id, TVGuard)
#         if not TVGuard(plg_prefs):
#             return
#         kv_fields = {}
#         for field_name in






# class PluginPref(t.Generic[PluginType]):
#     """Base class for preferences of a plugin."""

#     plg: "Plugin[PluginType]"
#     """Backward reference to the plugin to which these preferences belong."""

#     def __init__(self, plg: "Plugin[PluginType]"):
#         self.plg = plg

#     def serialize(self) -> PrefDataStruct:
#         pref_data: PrefDataType = PrefDataType()

#         # If Plugin.active does not match the default, the value is added to the
#         # preferences; otherwise, this is not necessary.
#         if self.plg.active != self.plg.cfg.active:
#             pref_data.active = BoolCatalog.serialize(self.plg.active)

#         return PrefDataStruct(plugins={self.plg.id: pref_data})

#     def load(self, preferences: PrefDataStruct):

#         if pref_data.active is not None:




#             and  != pref_data.active:




#         active = pref_data.get("active", TVGuard)
#         if TVGuard(active):
#             # FIXME: TVGuard funktioniert nicht, weil isinstance(y, BoolLiterals) auch nicht funktioniert.
#             self.plg.active = BoolCatalog.get_value(x)

#         if isinstance(active, BoolLiterals):
#             pass










# PluginsStorageCfg = dict[str, PluginCfg]
