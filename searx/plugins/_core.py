# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=too-few-public-methods
""".. sidebar:: Further reading ..

   - :ref:`plugins generic`

Plugins can extend or replace functionality of various components of SearXNG.

Entry points (hooks) define when a plugin runs.  Right now only three hooks are
implemented.  So feel free to implement a hook if it fits the behaviour of your
plugin.  A plugin doesn't need to implement all the hooks.

- pre search: :py:obj:`Plugin.pre_search`
- post search: :py:obj:`Plugin.post_search`
- on each result item: :py:obj:`Plugin.on_result`

"""

from __future__ import annotations

__all__ = ["PluginInfo", "Plugin", "PluginStorage"]

import types
import sys
import typing
import abc
from dataclasses import dataclass, field
import pathlib
import logging

import flask

from searx.utils import load_module
from searx.result_types import Result


if typing.TYPE_CHECKING:
    from searx.search import SearchWithPlugins


_default = pathlib.Path(__file__).parent
log: logging.Logger = logging.getLogger("searx.plugins")


@dataclass(kw_only=True)
class PluginInfo:
    """Object that holds informations about a *plugin*, these infos are shown to
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

    preference_section: typing.Literal["general", "ui", "privacy", "query"] | None
    """Section (tab/group) in the preferences where this plugin is shown to the
    user.

    The value ``query`` is reserved for plugins that are activated via a
    *keyword* as part of a search query, see:

    - :py:obj:`PluginInfo.examples`
    - :py:obj:`Plugin.keywords`

    Those plugins are shown in the preferences in tab *Special Queries*.
    """

    examples: list[str] = field(default_factory=list)
    """List of short examples of the usage / of query terms."""

    keywords: list[str] = field(default_factory=list)
    """See :py:obj:`Plugin.keywords`"""


class Plugin(abc.ABC):
    """Base class of all Plugins."""

    default_on: bool
    """Plugin is enabled/disabled by default."""

    keywords: list[str] = []
    """Keywords in the search query that activate the plugin.  The *keyword* is
    the first word in a search query.  If a plugin should be executed regardless
    of the search query, the list of keywords should be empty (which is also the
    default)."""

    log: logging.Logger
    """A logger object, is automatically initialized when calling the
    constructor (if not already set in the subclass)."""

    id: str = ""
    """The ID (suffix) in the HTML form e.g. ``oa_doi_rewrite``."""

    def __init__(self) -> None:
        super().__init__()

        if not self.id:
            self.id = f"{self.__class__.__module__}.{self.__class__.__name__}"
        if not getattr(self, "log", None):
            self.log = log.getChild(self.id)

    def __hash__(self) -> int:
        """The hash value is used in :py:obj:`set`, for example, when an object
        is added to the set.  The hash value is also used in other contexts,
        e.g. when checking for equality to identify identical plugins from
        different sources (name collisions)."""

        return id(self)

    def __eq__(self, other):
        """py:obj:`Plugin` objects are equal if the hash values of the two
        objects are equal."""

        return hash(self) == hash(other)

    def init(self, app: flask.Flask) -> bool:  # pylint: disable=unused-argument
        """Initialization of the plugin, the return value decides whether this
        plugin is active or not.  Initialization only takes place once, at the
        time the WEB application is set up.  The base methode always returns
        ``True``, the methode can be overwritten in the inheritances,

        - ``True`` plugin is active
        - ``False`` plugin is inactive
        """
        return True

    @abc.abstractmethod
    def pre_search(self, request: flask.Request, search: "SearchWithPlugins") -> bool:
        """Runs BEFORE the search request and returns a boolean:

        - ``True`` to continue the search
        - ``False`` to stop the search
        """

    @abc.abstractmethod
    def on_result(self, request: flask.Request, search: "SearchWithPlugins", result: Result) -> bool:
        """Runs for each result of each engine and returns a boolean:

        - ``True`` to keep the result
        - ``False`` to remove the result from the result list

        The ``result`` can be modified to the needs.

        .. hint::

           I :py:obj:`Result.url` is modified, :py:obj:`Result.parsed_url` must
           be changed accordingly:

           .. code:: python

              result["parsed_url"] = urlparse(result["url"])
        """

    @abc.abstractmethod
    def post_search(self, request: flask.Request, search: "SearchWithPlugins") -> None | list[Result]:
        """Runs AFTER the search request.  Can return a list of :py:obj:`Result`
        objects to be added to the final result list."""

    @abc.abstractmethod
    def info(self) -> PluginInfo:
        """Returns a dictioniary with infos shown to the user in the preference
        menu."""


class ModulePlugin(Plugin):
    """A wrapper class for legacy *plugins*.

    .. note::

       In a module plugin, the follwing names are mapped:

       - `module.query_keywords` --> :py:obj:`Plugin.keywords`
       - `module.plugin_id` --> :py:obj:`Plugin.id`
       - `module.logger` --> :py:obj:`Plugin.log`
    """

    _required_attrs = (("name", str), ("description", str), ("default_on", bool))

    def __init__(self, mod: types.ModuleType):
        """In case of missing attributes in the module, the runtime application
        exit with error (3)."""

        self.module = mod
        self.id = getattr(self.module, "plugin_id", self.module.__name__)
        self.log = logging.getLogger(self.module.__name__)
        self.keywords = getattr(self.module, "query_keywords", [])

        for attr, attr_type in self._required_attrs:
            if not hasattr(self.module, attr):
                self.log.critical("missing attribute '%s', cannot load plugin", attr)
                sys.exit(3)
            if not isinstance(getattr(self.module, attr), attr_type):
                self.log.critical("attribute '%s' is not of type %s", attr, attr_type)
                sys.exit(3)

        self.default_on = mod.default_on

        # monkeypatch module
        self.module.logger = self.log  # type: ignore

        super().__init__()
        self.log.debug("plugin has been loaded")

    def init(self, app: flask.Flask) -> bool:
        if not hasattr(self.module, "init"):
            return True
        return self.module.init(app)

    def pre_search(self, request: flask.Request, search: "SearchWithPlugins") -> bool:
        if not hasattr(self.module, "pre_search"):
            return True
        return self.module.pre_search(request, search)

    def on_result(self, request: flask.Request, search: "SearchWithPlugins", result: Result) -> bool:
        if not hasattr(self.module, "on_result"):
            return True
        return self.module.on_result(request, search, result)

    def post_search(self, request: flask.Request, search: "SearchWithPlugins") -> None | list[Result]:
        if not hasattr(self.module, "post_search"):
            return None
        return self.module.post_search(request, search)

    def info(self) -> PluginInfo:
        return PluginInfo(
            id=self.id,
            name=self.module.name,
            description=self.module.description,
            preference_section=getattr(self.module, "preference_section", None),
            examples=getattr(self.module, "query_examples", []),
            keywords=self.keywords,
        )


class PluginStorage:
    """A storage for managing the *plugins* of SearXNG."""

    plugin_list: set[Plugin]
    """The list of :py:obj:`Plugins` in this storage."""

    def __init__(self):
        self.plugin_list = set()

    def __iter__(self):

        yield from self.plugin_list

    def __len__(self):
        return len(self.plugin_list)

    @property
    def info(self) -> list[PluginInfo]:
        return [p.info() for p in self.plugin_list]

    def load_builtins(self):
        """Loads plugin modules from the python packages in :origin:`searx/plugins`.
        The python modules are wrapped by :py:obj:`ModulePlugin`."""

        for f in _default.iterdir():
            if f.name.startswith("_"):
                continue
            mod = load_module(f.name, str(f.parent))
            self.register(ModulePlugin(mod))

    def register(self, plugin: Plugin):
        """Register a :py:obj:`Plugin` in case of name collision (if two plugins
        have same ID) the runtime application exit with error (3)."""

        if plugin in self.plugin_list:
            plugin.log.critical(f"name collision '{plugin.id}'")
            sys.exit(3)

        self.plugin_list.add(plugin)

    def init(self, app: flask.Flask) -> None:
        """Calls the method :py:obj:`Plugin.init` of each plugin in this
        storage.  Depending on its return value, the plugin is removed from
        *this* storage or not."""

        for plg in self.plugin_list.copy():
            if not plg.init(app):
                self.plugin_list.remove(plg)

    def pre_search(self, request: flask.Request, search: "SearchWithPlugins") -> bool:

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

    def on_result(self, request: flask.Request, search: "SearchWithPlugins", result: Result) -> bool:

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

    def post_search(self, request: flask.Request, search: "SearchWithPlugins") -> None:
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
