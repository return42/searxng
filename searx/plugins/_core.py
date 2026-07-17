# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, too-few-public-methods

import typing as t
from collections import abc as c_abc

import abc
import importlib
import inspect
import logging

import msgspec
import flask
from flask_babel import LazyString  # type: ignore[reportMissingTypeStubs]

from searx.extended_types import SXNG_Request
from searx import prefs, forms

if t.TYPE_CHECKING:
    from searx.search import SearchWithPlugins
    from searx.result_types import Result, ResultList

log: logging.Logger = logging.getLogger("searx.plugins")


PrefSection: t.TypeAlias = t.Literal["general", "ui", "privacy", "query", None]
"""Section (tab/group) in the preferences where this plugin is shown to the
user.

The value ``query`` is reserved for plugins that are activated via a *keyword*
as part of a search query, see:

- :py:obj:`PluginInfo.examples`
- :py:obj:`Plugin.keywords`

Those plugins are shown in the preferences in tab *Special Queries*.
"""

PREF_SECTIONS: list[PrefSection] = list(t.get_args(PrefSection))
"""List off prefernces sections (:obj:`PrefSection`)"""

# Configuration of a plugin
# -------------------------


class PluginCfg(msgspec.Struct):
    """Base class for the individual configuration of all types of plugins."""


PluginCfgTypeT = t.TypeVar("PluginCfgTypeT", bound=PluginCfg)


class StoragePlgCfg(msgspec.Struct):
    """A plugin configuration in the list of configured Plugins.

    .. code:: yaml

       plugins:                       # <-- Storage.load_settings(StorageCfg)
         # ...
         mypackage.mymodule.MyPlugin: # <-- Plugin[<plugin-id>] / base class: StoragePlgCfg
           active: true
           locked: false              # lock preferences
           cfg:                       # <-- Plugin.cfg / base class: PluginCfg
             option_a: 42
             option_b:
                - "foo"
                - "bar"
    """

    active: bool = True
    """Plugin is "on" by default and the user can *opt-out* in the preferences
    :py:obj:`Plugin.active`."""

    locked: bool = False
    """Plugin's preference are un-locked by default (:py:obj:`Plugin.locked`)."""

    cfg: dict[str, t.Any] = msgspec.field(default_factory=dict)


# Preferences of a plugin
# -----------------------


class PluginPref(prefs.Pref[forms.ValT], t.Generic[forms.ValT]):

    name: str
    """Name of the plugin preference."""

    plg: "PluginType"
    """Plugin to which this preference belongs."""

    def __init__(
            self,
            name: str,
            plg: "Plugin[t.Any, t.Any, t.Any]",
            default: c_abc.Sequence[forms.ValT] | forms.ValT,
            catalog: forms.Catalog[forms.ValT] | forms.CatalogDefType[forms.ValT] | None = None,
            l10n_descr: LazyString | str = "",
    ):

        self.name = name
        self.plg = plg

        super().__init__(
            id=f"{plg.id}_{name}",
            default=default,
            catalog=catalog,
            locked=plg.locked,
            l10n_descr=l10n_descr,
        )


# Representation of the plugin in the UI
# --------------------------------------


class PluginInfo:
    """Object that holds information about a *plugin*, these infos are shown to
    the user in the Preferences menu.

    To be able to translate the information into other languages, the text must
    be written in English and translated with :py:obj:`flask_babel.lazy_gettext`.
    """

    id: str
    """The ID-selector in HTML/CSS `#<id>` (default is :py:obj:`Plugin.id`)."""

    name: LazyString
    """Name of the *plugin*."""

    description: LazyString
    """Short description of the *answerer*."""

    preference_section: PrefSection | None = "general"
    """Section (tab/group) in the preferences where this plugin is shown to the
    user.

    The value ``query`` is reserved for plugins that are activated via a
    *keyword* as part of a search query, see:

    - :py:obj:`PluginInfo.examples`
    - :py:obj:`Plugin.keywords`

    Those plugins are shown in the preferences in tab *Special Queries*.
    """

    examples: list[str] = []
    """List of short examples of the usage / of query terms."""

    keywords: list[str] = []
    """See :py:obj:`Plugin.keywords`"""

    def __init__(self, plg: "Plugin[t.Any, t.Any]"):
        self.plg: "Plugin[t.Any, t.Any]" = plg
        self.id = plg.id
        self.keywords = plg.keywords


PluginInfoTypeT = t.TypeVar("PluginInfoTypeT", bound=PluginInfo)

# Plugin instances at runtime
# ---------------------------


class Plugin(abc.ABC, t.Generic[PluginInfoTypeT, PluginCfgTypeT]):
    """Abstract base class of all Plugins."""

    id: str = ""
    """The ID used in the HTML form and as cookie name
    (:obj:`prefs.PREF_ID_PATTERN`).
    """
    active: bool
    """Plugin is enabled/disabled by default (:py:obj:`StoragePlgCfg.active`)."""

    locked: bool
    """Plugin's preference are un-locked by default (:py:obj:`StoragePlgCfg.locked`)."""

    keywords: list[str] = []
    """Keywords in the search query that activate the plugin.  The *keyword* is
    the first word in a search query.  If a plugin should be executed regardless
    of the search query, the list of keywords should be empty (which is also the
    default in the base class for Plugins)."""

    info_factory: t.ClassVar[type[PluginInfo]]
    info: PluginInfoTypeT
    """Information about the *plugin*, see :py:obj:`PluginInfo`."""

    cfg_factory: t.ClassVar[type[PluginCfg]] = PluginCfg
    cfg: PluginCfgTypeT
    """Configuration (setup) of the *plugin*, see :py:obj:`PluginCfg`."""

    log: logging.Logger
    """A logger object, is automatically initialized when calling the
    constructor (if not already set in the subclass)."""

    fqn: str

    # will be annotated in the sub-classes
    prefs = {}  # pyright: ignore[reportUnannotatedClassAttribute]

    def __init__(self, storage_plg_item: dict[str, t.Any]) -> None:

        if not getattr(self, "info_factory"):
            raise NotImplementedError(f"plugin {self} is missing attribute 'info_factory'")
        if not self.id:
            raise NotImplementedError(f"plugin {self} is missing attribute 'id'")
        if not forms.FIELD_ID_PATTERN.fullmatch(self.id):
            raise ValueError(f"plugin ID {self.id} contains invalid character (use lowercase ASCII)")
        if not getattr(self, "log", None):
            pkg_name = inspect.getmodule(self.__class__).__package__  # type: ignore[reportOptionalMemberAccess]
            self.log = logging.getLogger(f"{pkg_name}.{self.id}")

        self.fqn = self.__class__.__mro__[0].__module__

        # Initially, the on/off state is taken from the configuration (StoragePlgCfg)
        storage_plg = StoragePlgCfg(**storage_plg_item)  # type: ignore[reportAny]
        self.active = storage_plg.active
        self.locked = storage_plg.locked

        self.cfg = t.cast(PluginCfgTypeT, self.cfg_factory(**storage_plg.cfg))
        self.info = t.cast(PluginInfoTypeT, self.info_factory(self))

    def init(self):
        self.prefs = {}

    # @property
    # def prefs(self) -> PrefMap:
    #     """Provides the individual preferences for this plugin and may need to
    #     be adjusted in the heirs if they have special preferences.
    #     """
    #     return self._prefs

    def __hash__(self) -> int:
        """The hash value is used in :py:obj:`set`, for example, when an object
        is added to the set.  The hash value is also used in other contexts,
        e.g. when checking for equality to identify identical plugins from
        different sources (name collisions)."""

        return id(self)

    def __eq__(self, other: t.Any):  # type: ignore[reportAny]
        """py:obj:`Plugin` objects are equal if the hash values of the two
        objects are equal."""

        return hash(self) == hash(other)  # type: ignore[reportAny]

    # pylint: disable=unused-argument
    def init_from_app(self, app: flask.Flask) -> bool:  # type: ignore[reportUnusedParameter]
        """Initialization of the plugin in application's context.

        Initialization only takes place once, at the time the WEB application is
        set up.  The return value decides whether this plugin is available in
        the application or not. Don't mess with *active/inactive* state of a
        plugin:

        - ``True``: plugin is available in the application. If a plugin is
           available in the application, it can be *active* or *inactive*.

        - ``False`` plugin is NOT available in the application.  If a plugin is
           not available in the application, then it cannot be *active*.
           either.

        The method can be overridden; however, the method in the base class
        should always be checked as well (necessary for future developments
        within the base class).
        """

        # FIXME: die Plugins haben bis hier in die Einstellungen aus der
        # Konfiguration (settings.yml).  Die Erben der Plugin Klasse können
        # diese init-Methode überschreiben um ggf. aus dem Anwendungskontext
        # (der Flask app) weitere Initialisierungen vorzunehmen
        #
        # FIXME: Was bisher noch fehlt ist eine Methode
        # (Plugin.init_from_request), die hier in der Basisklsase noch eine
        # Initialisierung aus dem Request Kontext (z.B. aus den Cookies) vornimmt.
        return True

    def pre_search(
        self,
        request: SXNG_Request,  # type: ignore[reportUnusedParameter]
        search: "SearchWithPlugins",  # type: ignore[reportUnusedParameter]
    ) -> bool:
        """Runs BEFORE the search request and returns a boolean:

        - ``True`` to continue the search
        - ``False`` to stop the search
        """
        return True

    def on_result(
        self,
        request: SXNG_Request,  # type: ignore[reportUnusedParameter]
        search: "SearchWithPlugins",  # type: ignore[reportUnusedParameter]
        result: "Result",  # type: ignore[reportUnusedParameter]
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
        self,
        request: SXNG_Request,  # pyright: ignore[reportUnusedParameter]
        search: "SearchWithPlugins",  # pyright: ignore[reportUnusedParameter]
    ) -> "None | ResultList":
        """Runs AFTER the search request.  Can return a list of
        :py:obj:`Result <searx.result_types._base.Result>` objects to be added to the
        final result list."""
        return


PluginType: t.TypeAlias = Plugin[PluginInfo, PluginCfg]
PluginTypeT = t.TypeVar("PluginTypeT", bound=PluginType)


class StorageCfg(dict[str, dict[str, t.Any]]):
    pass


class Storage:
    """A storage for managing the *plugins* of SearXNG."""

    def __init__(self):
        self._by_id: dict[str, PluginType] = {}

    def __len__(self):
        return len(self._by_id)

    def __iter__(self) -> c_abc.Generator[PluginType]:
        yield from self._by_id.values()

    def items(self) -> list[tuple[str, PluginType]]:
        return [i for i in self._by_id.items()]

    def get(self, plg_id: str) -> PluginType | None:
        return self._by_id.get(plg_id, None)

    def section(self, name: PrefSection) -> c_abc.Sequence[PluginType]:
        """Returns the list of plugins in a preference section
        (:obj:`PrefSection`)."""
        return [plg for plg in self if plg.info.preference_section == name]

    def register(self, plg: PluginType):
        """Register a :py:obj:`Plugin`.  In case of name collision (if two
        plugins have same ID) a :py:obj:`KeyError` exception is raised.
        """
        if self.get(plg.id):
            msg = f"name collision '{plg.id}'"
            plg.log.critical(msg)
            raise KeyError(msg)
        self._by_id[plg.id] = plg
        plg.log.debug("plugin has been loaded")

    def load_settings(self, cfg: StorageCfg):
        """Load plugins configured in SearXNG's settings :ref:`settings
        plugins`."""

        for fqn, plg_cfg in cfg.items():
            cls: type[PluginType] | None = None
            mod_name, cls_name = fqn.rsplit(".", 1)
            try:
                mod = importlib.import_module(mod_name)
                cls = getattr(mod, cls_name, None)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                log.exception(exc)

            if cls is None:
                msg = f"plugin {fqn} is not implemented"
                raise ValueError(msg)
            plg = cls(plg_cfg)
            self.register(plg)

    def init_from_app(self, app: flask.Flask) -> None:
        """Calls the method :py:obj:`Plugin.init` of each plugin in this
        storage.  Depending on its return value, the plugin is removed from
        *this* storage or not."""

        for plg_id, plg_obj in self.items():
            if not plg_obj.init_from_app(app):
                del self._by_id[plg_id]

    def pre_search(self, request: SXNG_Request, search: "SearchWithPlugins") -> bool:
        """Calls the handle :obj:`Plugin.pre_search` for the plugins in this
        search query and stops as soon as a plugin returns `False`.
        """
        ret = True
        for plg in [p for p in self if p.id in search.user_plugins]:
            try:
                ret = bool(plg.pre_search(request=request, search=search))
            except Exception:  # pylint: disable=broad-except
                plg.log.exception("Exception while calling pre_search")
                continue
            if not ret:
                # skip this search on the first False from a plugin
                break
        return ret

    def on_result(self, request: SXNG_Request, search: "SearchWithPlugins", result: "Result") -> bool:
        """Calls the handle :obj:`Plugin.on_result` for the plugins in this
        search query and discards the :obj:`.Result` item as soon as a plugin
        returns `False`.
        """
        ret = True
        for plg in [p for p in self if p.id in search.user_plugins]:
            try:
                ret = bool(plg.on_result(request=request, search=search, result=result))
            except Exception:  # pylint: disable=broad-except
                plg.log.exception("Exception while calling on_result")
                continue
            if not ret:
                # ignore this result item on the first False from a plugin
                break

        return ret

    def post_search(self, request: SXNG_Request, search: "SearchWithPlugins") -> None:
        """Extend :obj:`searx.search.Search.result_container` with result
        items from plugins listed in :obj:`searx.search.SearchWithPlugins.user_plugins`.
        """

        keyword = None
        for keyword in search.search_query.query.split():
            if keyword:
                break

        for plg in [p for p in self if p.id in search.user_plugins]:

            if plg.keywords:
                # plugin with keywords: skip plugin if no keyword match
                if keyword and keyword not in plg.keywords:
                    continue
            try:
                results: ResultList | None = plg.post_search(request=request, search=search)
            except Exception:  # pylint: disable=broad-except
                plg.log.exception("Exception while calling post_search")
                continue

            if results is None:
                continue
            # In case of *plugins* prefix ``plugin:`` is set, see searx.result_types.Result
            search.result_container.extend(engine_name="plugin: {plg.id}", results=results)
