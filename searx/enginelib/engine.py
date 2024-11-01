# SPDX-License-Identifier: AGPL-3.0-or-later
"""Implementation of the :py:obj:`Engine` and :py:obj:`EngineModule` class."""

from __future__ import annotations

__all__ = ["Engine", "EngineModule"]

from typing import Any

import importlib
import inspect
import logging
import numbers
import pathlib
import types
import typing

import msgspec

import searx.utils
from searx import logger as log, get_setting
from .traits import EngineTraitsMap, EngineTraits

if typing.TYPE_CHECKING:
    from . import traits


log: logging.Logger = log.getChild("enginelib.engine")
ENGINES_FOLDER = pathlib.Path(__file__).parent.parent / "engines"
TRAIT_MAP = None


INHERIT_OUTGOING = [
    ("timeout", "request_timeout", lambda x: x),
    ("enable_http", "enable_http2", lambda x: not x),
    ("proxies", "proxies", lambda x: x),
    ("using_tor_proxy", "using_tor_proxy", lambda x: x),
    ("max_keepalive_connections", "pool_maxsize", lambda x: x),
    ("max_connections", "pool_connections", lambda x: x),
    ("keepalive_expiry", "keepalive_expiry", lambda x: x),
]


class Engine(msgspec.Struct, kw_only=True):
    """Class of engine instances build from YAML settings.

    Further documentation see :ref:`general engine configuration`.
    """

    # common engine settings ..

    name: str
    """Name that will be used across SearXNG to define this engine.  In settings, on
    the result page .."""

    engine: str
    """Name of the python file used to handle requests and responses to and from
    this search engine (file name from :origin:`searx/engines` without
    ``.py``)."""

    engine_type: typing.Literal[
        "online",
        "offline",
        "online_currency",
        "online_dictionary",
        "online_url_search",
    ] = "online"
    """Type of the engine (:ref:`searx.search.processors`)"""

    shortcut: str = ""
    """Code used to execute bang requests (``!foo``)"""

    categories: typing.List[str] = msgspec.field(default_factory=lambda: ["general"])
    """Specifies to which categories the engine should be added.  Engines can be
    assigned to multiple categories.

    .. _engine categories:

    Categories can be shown as tabs (:ref:`settings categories_as_tabs`) in the
    UI.  A search in a tab (in the UI) will query all engines that are active in
    this tab.  In the preferences page (``/preferences``) -- under *engines* --
    users can select what engine should be active when querying in this tab.

    Alternatively, :ref:`!bang <search-syntax>` can be used to search all engines
    in a category, regardless of whether they are active or not, or whether they
    are in a tab of the UI or not.  For example, ``!dictionaries`` can be used to
    query all search engines in that category (group)."""

    timeout: float = 3
    """Timeout of a search with the search engine, default value is
    ``request_timeout`` from :ref:`settings outgoing`.  **Be careful, it will
    modify the global timeout of SearXNG, when the engine is used in a query.**"""

    disabled: bool = False
    """To disable by default the engine, but not deleting it.  It will allow the
    user to manually activate it in the settings."""

    inactive: bool = False
    """Remove the engine from the settings (*disabled & removed*)."""

    weight: int = 1
    """Weighting of the results of this engine."""

    display_error_messages: bool = True
    """When an engine returns an error, the message is displayed on the user interface."""

    paging: bool = False
    """Engine supports multiple pages."""

    max_page: int = 0
    """Maximum page number.  The page numbering starts with 1, which is why 1
    means that no (further) pages are offered (better to set `paging=False`).
    The value 0 stands for any number of pages."""

    time_range_support: bool = False
    """Engine supports search time range."""

    safesearch: bool = False
    """Engine supports SafeSearch"""

    # Language & Region settings ..

    language_support: bool = False
    """Engine supports languages (locales) search."""

    language: str = ""
    """For an engine, when there is ``language: ...`` in the YAML settings the engine
    does support only this one language:

    .. code:: yaml

      - name: google french
        engine: google
        language: fr
    """

    region: str = ""
    """For an engine, when there is ``region: ...`` in the YAML settings the engine
    does support only this one region::

    .. code:: yaml

      - name: google belgium
        engine: google
        region: fr-BE
    """

    about: dict = {}
    """Additional fields describing the engine.

    .. code:: yaml

       about:
          website: https://example.com
          wikidata_id: Q306656
          official_api_documentation: https://example.com/api-doc
          use_official_api: true
          require_api_key: true
          results: HTML
    """

    # settings offered by some engines ..

    api_key: str | None = None
    """In a few cases, using an API needs the use of a secret key.  How to obtain them
    is described in the engine implementation."""

    base_url: str | None = None
    """Part of the URL that should be stable across every request.  Can be
    useful to use multiple sites using only one engine, or updating the site URL
    without touching at the code."""

    # private engines ..

    tokens: typing.List[str] = []
    """A list of secret tokens to make this engine *private*, more details see
    :ref:`private engines`."""

    # HTTP settings ..

    enable_http: bool = False
    """Enable HTTP for the engine (by default only HTTPS is enabled)."""

    send_accept_language_header: bool = False
    """Several engines that support languages (or regions) deal with the HTTP
    header ``Accept-Language`` to build a response that fits to the locale.
    When this option is activated, the language (locale) that is selected by the
    user is used to build and send a ``Accept-Language`` header in the request
    to the origin search engine."""

    retry_on_http_error: bool | int | typing.List = False
    """Retry request on some HTTP status code.

    Example:

    * ``true`` : on HTTP status code between 400 and 599.
    * ``403`` : on HTTP status code 403.
    * ``[403, 429]``: on HTTP status code 403 and 429.
    """

    # Network settings ..

    network: str | None = None
    """Use the network configuration from another engine.

    In addition, there are two default networks:

    - ``ipv4`` set ``local_addresses`` to ``0.0.0.0`` (use only IPv4 local addresses)
    - ``ipv6`` set ``local_addresses`` to ``::`` (use only IPv6 local addresses)
    """

    proxies: dict | str | None = None
    """Set proxies for a specific engine, default value is ``proxies`` from
    :ref:`settings outgoing`.

    .. code:: yaml

       proxies :
         http:  socks5://proxy:port
         https: socks5://proxy:port
    """

    using_tor_proxy: bool = False
    """Using tor proxy (``true``) or not (``false``) for the engine, default
    value is ``using_tor_proxy`` from :ref:`settings outgoing`."""

    # HTTPX Resource Limits ..

    max_keepalive_connections: int | None = None
    """`Pool limit configuration`_.  Number of allowable keep-alive connections,
    default value is ``pool_maxsize`` from :ref:`settings outgoing`.

    .. _Pool limit configuration: https://www.python-httpx.org/advanced/resource-limits/
    """

    max_connections: int | None = None
    """`Pool limit configuration`_.  Maximum number of allowable connections,
    default value is ``pool_connections`` from :ref:`settings outgoing`."""

    keepalive_expiry: numbers.Real | None = None
    """`Pool limit configuration`_.  Time limit on idle keep-alive connections
    in seconds, default value is ``keepalive_expiry`` from :ref:`settings
    outgoing`."""

    # for internal usage

    fetch_traits: typing.Callable | None = None
    """Function to to fetch engine's traits from origin."""

    traits: traits.EngineTraits
    """Traits of the engine."""

    settings: dict
    """Configuration of engine instance, settings from the :ref:`settings.yml
    <settings engine>`"""

    logger: logging.Logger
    """A logger object (:py:obj:`logging.Logger`) for the engine."""

    @staticmethod
    def from_engine_settings(engine_settings: dict[str, Any]) -> 'Engine':
        """Factory to build a :py:obj:`Engine` instance from ``engine_settings``.

        :param dict engine_settings: Attributes from YAML ``settings:engines/[<engine_settings>, ..]``
        :return: fully initialized :py:obj:`Engine` instance build up from ``engine_settings``.

        1. check mandatory fields in ``engine_settings`` and prepare ``engine_settings``
        2. set engine's :py:obj:`engine_settings["traits"] <Engine.traits>`
        3. set engine's :py:obj:`engine_settings["module"] <Engine.module>`
        4. an engine instances is created from the now prepared ``engine_settings``

        If an instance cannot be built, the exception causing this is not
        caught.  If (mandatory) fields are not valid, a :py:obj:`ValueError`
        exception is usually thrown:

        - engine's ``name`` is not set or contains underscore
        - ``engines_settings`` contains a field that can't be customized
        - A required field is missing in ``engines_settings`` (which is
          initialized by ``None`` in engine's python module).
        """

        fqn = engine_settings.get("engine")
        if fqn is None:
            raise ValueError(f"enigne_settings: the mandatory field 'engine' is missing! {engine_settings}")

        if "." not in fqn:
            # engine-legacy: implemented in a python module searx.engines.*
            EngineModule.prepare_settings(engine_settings)
            kwargs = {k: v for k, v in engine_settings.items() if k in EngineModule.__struct_fields__}
            return EngineModule(settings=engine_settings, **kwargs)

        # fqn is a inheritance of class Engine
        mod_name, _, func_name = fqn.rpartition('.')
        mod = importlib.import_module(mod_name)
        cls: Engine = getattr(mod, func_name)
        if cls is None:
            raise ValueError(f"engine {fqn} is not implemented")
        cls.prepare_settings(engine_settings)
        kwargs = {k: v for k, v in engine_settings.items() if k in EngineModule.__struct_fields__}
        return cls(settings=engine_settings, **kwargs)

    @classmethod
    def prepare_settings(cls, engine_settings: dict[str, Any]) -> None:

        cls._prepare_settings(engine_settings)
        cls._set_traits(engine_settings)

    def __post_init__(self):
        """Initialize ``Engine`` instance.  A replacement for ``__init__``,
        which must not be overridden in the inheriting classes, see `Post-Init
        Processing`_.  TIP: most often its recommended to overwrite the
        ``init()`` method in the inheriting classes.

        .. Post-Init Processing: https://jcristharif.com/msgspec/structs.html#post-init-processing

        """
        pass  # pylint: disable=unnecessary-pass

    @property
    def init_required(self) -> bool:
        return True

    def init(self):
        """Additions to the instance (initialization), the additions can be
        overwritten in the inheriting classes."""
        pass  # pylint: disable=unnecessary-pass

    @classmethod
    def _prepare_settings(cls, engine_settings: dict[str, Any]) -> None:

        if not engine_settings.get("name"):
            raise ValueError(f"enigne_settings: the mandatory field 'name' is missing! {engine_settings}")

        name = engine_settings["name"]
        if '_' in name:
            raise ValueError(f"Engine's instance 'name' contains underscore: {name}")

        if name.lower() != name:
            log.warning("Engine's instance 'name' '%s' is not lowercase, converting to lower", name)
            engine_settings["name"] = name.lower()

        # engine settings that can't be customized (defined in engine's
        # implementation or provided by the framework)
        for opt in ["engine_type", "fetch_traits", "traits", "settings"]:
            if engine_settings.get(opt, msgspec.UNSET) != msgspec.UNSET:
                raise ValueError(f"engine {engine_settings['name']}: {opt} can't be customized")

        engine_settings["logger"] = log.getChild(engine_settings["name"])

        # normalize categories to a list of category names
        if engine_settings.get("categories", msgspec.UNSET) != msgspec.UNSET:
            field_val = engine_settings["categories"]
            if isinstance(field_val, str):
                field_val = list(map(str.strip, field_val.split(',')))
            engine_settings["categories"] = field_val

        # engine settings with defaults from "outgoing:" setting
        for opt, out_name, val_func in INHERIT_OUTGOING:
            if engine_settings.get(opt, msgspec.UNSET) == msgspec.UNSET:
                val = val_func(get_setting("outgoing." + out_name))
                engine_settings[opt] = val

        # engine settings from default or engine_setting
        for field_name in cls.__struct_fields__:
            #  1. configured in the engine_settings
            #  2. or defined via the default (remove it from the engine_settings)
            field_val = engine_settings.get(field_name, msgspec.UNSET)
            if field_val == msgspec.UNSET:
                engine_settings.pop(field_name, None)

    @classmethod
    def _set_traits(cls, engine_settings: dict[str, Any]) -> None:
        # set traits

        global TRAIT_MAP  # pylint: disable=global-statement
        if not TRAIT_MAP:
            TRAIT_MAP = EngineTraitsMap.from_data()

        engine_traits = EngineTraits(data_type='traits_v1')
        if engine_settings["name"] in TRAIT_MAP.keys():
            engine_traits = TRAIT_MAP[engine_settings["name"]]

        elif engine_settings["engine"] in TRAIT_MAP.keys():
            # The key of the dictionary traits_map is the *engine name*
            # configured in settings.yml.  When multiple engines are configured
            # in settings.yml to use the same origin engine (python module)
            # these additional engines can use the languages from the origin
            # engine.  For this use the configured ``engine: ...`` from
            # settings.yml
            engine_traits = TRAIT_MAP[engine_settings["engine"]]

        if engine_traits.data_type == 'traits_v1':
            cls._set_traits_v1(engine_settings, engine_traits)
        else:
            raise TypeError('engine traits of type %s is unknown' % engine_traits.data_type)

    @classmethod
    def _set_traits_v1(cls, engine_settings: dict[str, Any], engine_traits: EngineTraits) -> None:

        # set the copied & modified traits in engine's namespace
        engine_traits = engine_settings["traits"] = engine_traits.copy()

        _msg = "settings.yml - engine: '%s' / %s: '%s' not supported"

        # For an engine, when there is ``language: ...`` in the YAML settings
        # the engine does support only this one language::
        #
        #   - name: google french
        #     engine: google
        #     language: fr

        language = engine_settings.get("language")
        if language:
            if language not in engine_traits.languages.keys():
                raise ValueError(_msg % (engine_settings.get("name"), 'language', language))
            engine_traits.languages = {language: engine_traits.languages[language]}

        # For an engine, when there is ``region: ...`` in the YAML settings the engine
        # does support only this one region::
        #
        #   - name: google belgium
        #     engine: google
        #     region: fr-BE

        region = engine_settings.get("region")
        if region:
            if region not in engine_traits.regions.keys():
                raise ValueError(_msg % (engine_settings.get("name"), 'region', region))
            engine_traits.regions = {region: engine_traits.regions[region]}

        # set the copied & modified traits in engine's namespace
        engine_settings["language_support"] = bool(engine_traits.languages or engine_traits.regions)

    @property
    def is_active(self) -> bool:
        """Engine is active by default, except:

        - ``inactive`` is ``True``

        - engine is in category ``onions`` and not using tor / to exclude onion
          engines if not using tor

        """
        # check if engine is inactive
        if self.inactive is True:
            return False

        # exclude onion engines if not using tor
        if "onions" in self.categories and not self.using_tor_proxy:
            return False

        return True


class EngineModule(Engine):  # pylint: disable=too-few-public-methods
    """Specializations on the :py:obj:`Engine` class to read the implementation
    of a SearXNG engine from aPython module (searx.engines.<engine:>).
    Implementing a engine in a python module is the legacy method, a
    configuration looks like:

    .. code:: yaml

    - name: my online engine
      engine: demo_online     # engine is implemented in --> searx.engines.demo_online

    """

    # for internal usage

    module: types.ModuleType
    """A copy of the python module with the engine implementation, see
    :py:obj:`searx.utils.load_module`."""

    def __post_init__(self):

        # monkey patch engine's module

        for field_name in Engine.__struct_fields__:
            field_val = getattr(self, field_name)
            setattr(self.module, field_name, field_val)

        if self.settings.get("using_tor_proxy", msgspec.UNSET) != msgspec.UNSET:
            onion_url = self.settings.get("onion_url", msgspec.UNSET)
            if onion_url != msgspec.UNSET:
                # https://github.com/searxng/searxng/issues/1505#issuecomment-1183701938
                # has this ever been used, is there any engine that supports a
                # search_url (build up from "onion_url" and "search_path"):: The
                # feature was added in
                # https://github.com/searxng/searxng/commit/c3daa085376 today
                # its only supported by the xpath but has never been used in a
                # engine setting.
                setattr(self.module, "search_url", onion_url + self.settings.get("search_path", ""))
                setattr(self.module, "timeout", self.timeout + int(get_setting("outgoing.extra_proxy_timeout", 0)))
                self.search_url = self.module.search_url
                self.timeout = self.module.timeout

    @classmethod
    def prepare_settings(cls, engine_settings: dict[str, Any]) -> None:
        super(EngineModule, cls).prepare_settings(engine_settings)
        cls._set_module(engine_settings)

    @property
    def init_required(self) -> bool:
        return bool(getattr(self.module, "init", False))

    # https://docs.searxng.org/dev/engines/demo/demo_online.html

    def init(self):
        """Wrap module's ``init(..)`` function"""
        super().init()
        if getattr(self.module, "init", False):
            self.module.init(self.settings)

    def request(self, query, params):
        """Wrap module's ``request(..)`` function"""
        return self.module.request(query, params)

    def response(self, resp):
        """Wrap module's ``response(..)`` function"""
        return self.module.response(resp)

    # https://docs.searxng.org/dev/engines/offline_concept.html

    def search(self, query, params):
        """Wrap module's ``search(..)`` function"""
        ret_val = None
        if getattr(self.module, "search"):
            ret_val = self.module.search(query, params)
        return ret_val

    @classmethod
    def _set_module(cls, engine_settings: dict[str, Any]) -> None:
        # pylint: disable=too-many-branches

        mod_name = engine_settings["engine"]

        try:
            module = searx.utils.load_module(mod_name, ENGINES_FOLDER / f"{mod_name}.py")
        except (SyntaxError, KeyboardInterrupt, SystemExit, SystemError, ImportError, RuntimeError):
            log.exception(f"Fatal exception while loading engine module: {mod_name}")
            raise
        except BaseException:
            log.exception(f"Can't load engine module: {mod_name}")
            raise

        engine_settings["module"] = module
        engine_settings["fetch_traits"] = getattr(module, "fetch_traits", None)

        # probe unintentional name collisions / for example name collisions caused
        # by import statements in the engine module ..

        # network: https://github.com/searxng/searxng/issues/762#issuecomment-1605323861
        obj = getattr(module, "network", None)
        if obj and inspect.ismodule(obj):
            raise TypeError(f"type of {module.__name__}.network is a module ({obj.__name__}), expected a string")

        # remove engine settings that can't be customized if not also defined in the
        # module.

        for opt in ["base_url", "api_key"]:
            if opt in engine_settings and getattr(module, opt, msgspec.UNSET) == msgspec.UNSET:
                log.error(f"engine {engine_settings['name']}: ignore unknown option {opt}")
                engine_settings.pop(opt)

        # inherit "about" from the module ..
        about = getattr(module, "about", msgspec.UNSET)
        if about != msgspec.UNSET:
            about = about.copy()
            about.update(engine_settings.get("about", {}))

            setattr(module, "about", about)
            engine_settings["about"] = about

        # An attribute in the engine settings is required when its name in the
        # module doesn't start with ``_`` (underline).  Required attributes must
        # not be ``None``.

        for field_name in dir(module):
            if field_name.startswith("_"):
                continue

            field_val = engine_settings.get(field_name, getattr(module, field_name, None))
            if field_val is None:
                raise ValueError(f"Missing engine ({engine_settings['name']}) config attribute: {field_name}")

            setattr(module, field_name, field_val)

        # inherit fields from settings.yml or module

        for field_name in cls.__struct_fields__:

            # Hirachy of names, the value of the name is:
            #  1. configured in settings.yml
            field_val = engine_settings.get(field_name, msgspec.UNSET)

            #  2. defined in the module
            if field_val == msgspec.UNSET:
                field_val = getattr(module, field_name, msgspec.UNSET)

            if field_val == msgspec.UNSET:
                #  3. defined via the default
                engine_settings.pop(field_name, None)
            else:
                engine_settings[field_name] = field_val
