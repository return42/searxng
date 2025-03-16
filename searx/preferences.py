# SPDX-License-Identifier: AGPL-3.0-or-later
"""Implementation of SearXNG's preferences.
"""
from __future__ import annotations
import typing

import types

from flask_babel import lazy_gettext

import searx.engines
import searx.locales
import searx.plugins

from searx.extended_types import sxng_request
from searx import logger, get_setting, autocomplete, favicons
from searx.enginelib import Engine
from searx.engines import DEFAULT_CATEGORY

from .components import Form, FieldABC, Field, SingleChoice, Bool, SearchLocale, MultipleChoice, BoolGrp
from .settings_defaults import get_typedef

if typing.TYPE_CHECKING:
    import searx.client

log = logger.getChild("preferences")


class PluginStoragePrefs(BoolGrp):
    """The preferences for the plugins are feed from the :py:obj:`PluginStorage
    <searx.plugins.PluginStorage>`, the ``member_name`` of a plugin is the
    :py:obj:`Plugin.id <searx.plugins.Plugin.id>` of the plugin.
    """

    def __init__(self, form_id: str, grp_name: str, plg_storage: searx.plugins.PluginStorage):
        bool2str = {True: "1", False: "0"}
        members: dict[str, Bool] = {}
        for plg in plg_storage:
            field_name = self.sep.join([self.grp_name, plg.id])
            field = Bool(
                name=field_name,
                default=bool2str[plg.active],
                bool2str=bool2str,
            )
            field.form_id = self.form_id
            members[plg.id] = field

        super().__init__(form_id, grp_name, members)



class EngineMapPrefs(BoolGrp):
    """Engine preferences are similar to a :py:obj:`BooleanGroup`, but the special
    thing about these preferences is that an engine can be switched "on" within one
    category and "off" in another category.  The context of the categories is
    made up of the categories that are also configured as tabs (:ref:`settings
    categories_as_tabs`).
    """

    def __init__(self, form_id: str, grp_name: str, engines: list[Engine | types.ModuleType]):
        super().__init__(form_id, grp_name)
        self._engines = engines
        self.categories: dict[str, list[Bool]] = {}

    def init(self, prefs: Preferences):
        """Members of this group sorted by category name."""

        categs: set = {DEFAULT_CATEGORY}
        categs.update(get_setting("categories_as_tabs", {}).keys())  # type: ignore

        # build members by adding the category context and the name of the
        # engine to the field name.

        for eng in self._engines:

            # filter out engines with missing token
            if not prefs.validate_token(eng):
                continue

            for eng_categ in eng.categories:
                if eng_categ not in categs:
                    continue
                if eng_categ not in self.categories:
                    self.categories[eng_categ] = []

                # hint: the engine name may contain spaces, but the ID of HTML
                # element (e.g. <input id="...">) must not contain whitespaces!
                field_name = self.sep.join([eng_categ.replace(' ', '_'), eng.name.replace(' ', '_')])
                field = Bool(
                    name=field_name,
                    default=bool(not eng.disabled),
                    legend="",
                    description="",
                )
                self.members[eng.name] = field
                if self.categories.get(eng_categ) is None:
                    self.categories[eng_categ] = []
                self.categories[eng_categ].append(field)

        # sort the engines alphabetically since the order in settings.yml is meaningless.
        for l in self.categories.values():
            l.sort(key=lambda b: b.name)
        # ref to engines is no longer needed
        self._engines = []

    @property
    def disabled_engines(self) -> list[str]:
        return [eng_name for eng_name, field in self.members.items() if not field.value]


class Categories(MultipleChoice):

    def init(self, prefs: Preferences):

        # categories for which there is no active engine are filtered out.
        eng_pref: EngineMapPrefs = prefs["engines"]  # type: ignore
        eng_categs = eng_pref.categories.keys()

        for categ in self.str2obj.keys():
            if categ not in eng_categs:
                del self.str2obj[categ]

        # just to verify the defaults are any longer in catalog
        for val in self.default:
            self.val2str(val)


def sxng_pref_list() -> list[FieldABC | BoolGrp]:

    return [
        EngineMapPrefs("pref", "engines", list(searx.engines.engines.values())),
        PluginStoragePrefs("pref", "plugins", searx.plugins.STORAGE),
        SingleChoice(
            name="autocomplete",
            default=get_setting("search.autocomplete") or None,
            catalog={"-": None} | autocomplete.backends.items(),
            legend=lazy_gettext("Autocomplete"),
            description=lazy_gettext("Find stuff as you type"),
        ),
        Categories(
            name="categories",
            default={"general"},
            catalog={"general"} | set(get_setting("categories_as_tabs").keys()),
        ),
        Bool(
            name="center_alignment",
            default=get_setting("ui.center_alignment"),
            legend=lazy_gettext("Center Alignment"),
            description=lazy_gettext("Displays results in the center of the page (Oscar layout)."),
        ),
        SingleChoice(
            name="doi_resolver",
            default=get_setting("default_doi_resolver"),
            catalog=get_setting("doi_resolvers").keys(),
            legend=lazy_gettext("Open Access DOI resolver"),
            description=lazy_gettext("Select service used by DOI rewrite"),
        ),
        SingleChoice(
            name="favicon_resolver",
            default=get_setting("search.favicon_resolver") or "-",
            catalog={"-": None} | favicons.proxy.CFG.resolver_map,
            legend=lazy_gettext("Favicon Resolver"),
            description=lazy_gettext("Display favicons near search results"),
        ),
        SingleChoice(
            name="hotkeys",
            default=get_setting("ui.hotkeys") or "default",
            catalog=get_typedef("ui.hotkeys"),
            legend=lazy_gettext("Hotkeys"),
            description=lazy_gettext(
                """Navigate search results with hotkeys (JavaScript required). """
                """Press "h" key on main or result page to get help."""
            ),
            catalog_descr={
                "default": "SearXNG",
                "vim": lazy_gettext("Vim-like"),
            },
        ),
        Bool(
            name="image_proxy",
            default=get_setting("server.image_proxy"),
            legend=lazy_gettext("Image proxy"),
            description=lazy_gettext("Proxying image results through SearXNG"),
        ),
        Bool(
            name="infinite_scroll",
            default=get_setting("ui.infinite_scroll"),
            legend=lazy_gettext("Infinite scroll"),
            description=lazy_gettext("Automatically load next page when scrolling to bottom of current page"),
        ),
        SearchLocale(
            name="search_locale_tag",  # FIXME old name was "language"
            legend=lazy_gettext("Search language"),
            description=(
                lazy_gettext("What language do you prefer for search?")
                + lazy_gettext("Choose Auto-detect to let SearXNG detect the language of your query.")
            ),
        ),
        SingleChoice(
            name="ui_locale_tag",  # FIXME old name was "locale"
            default=sxng_request.client.ui_locale_tag,
            legend=lazy_gettext("Interface language"),
            description=lazy_gettext("Change the language of the layout"),
            catalog=set(searx.locales.LOCALE_NAMES.keys()),
            catalog_descr=searx.locales.LOCALE_NAMES,
        ),
        SingleChoice(
            name="method",
            default=get_setting("server.method"),
            catalog=get_typedef("server.method"),
            legend=lazy_gettext("HTTP Method"),
            description=lazy_gettext("Change how forms are submitted"),
        ),
        Bool(
            name="query_in_title",
            default=get_setting("ui.query_in_title"),
            legend=lazy_gettext("Query in the page's title"),
            description=lazy_gettext(
                "When enabled, the result page's title contains your query. Your browser can record this title"
            ),
        ),
        Bool(
            name="results_on_new_tab",
            default=get_setting("ui.results_on_new_tab"),
            legend=lazy_gettext("Results on new tabs"),
            description=lazy_gettext("Open result links on new browser tabs"),
        ),
        SingleChoice(
            name="safesearch",
            default=get_setting("server.safe_search"),
            catalog=get_typedef("server.safe_search"),
            legend=lazy_gettext("SafeSearch"),
            description=lazy_gettext("Filter content"),
            catalog_descr={
                "0": lazy_gettext("None"),
                "1": lazy_gettext("Moderate"),
                "2": lazy_gettext("Strict"),
            },
        ),
        Bool(
            name="search_on_category_select",
            default=get_setting("ui.search_on_category_select"),
            legend=lazy_gettext("Search on category select"),
            description=lazy_gettext(
                "Perform search immediately if a category selected. Disable to select multiple categories."
            ),
        ),
        SingleChoice(
            name="theme",
            default=get_setting("ui.default_theme"),
            catalog=get_typedef("ui.default_theme"),
            legend=lazy_gettext("Theme"),
            description=lazy_gettext("Change SearXNG layout"),
        ),
        SingleChoice(
            name="simple_style",
            default=get_setting("ui.theme_args.simple_style"),
            catalog=get_typedef("ui.theme_args.simple_style"),
            legend=lazy_gettext("Theme style"),
            description=lazy_gettext("Choose auto to follow your browser settings"),
        ),
        SingleChoice(
            name="url_formatting",
            default=get_setting("ui.url_formatting"),
            catalog=get_typedef("ui.url_formatting"),
            legend=lazy_gettext("URL formatting"),
            description=lazy_gettext("Change result URL formatting"),
            catalog_descr={
                "pretty": lazy_gettext("Pretty"),
                "full": lazy_gettext("Full"),
                "host": lazy_gettext("Host"),
            },
        ),
        Field(
            name="tokens",
            default="",
            legend=lazy_gettext("Engine tokens"),
            description=lazy_gettext("Access tokens for private engines"),
        ),
    ]


class Preferences(Form):
    """A collection of prefernces."""

    def __init__(self):
        super().__init__("pref", sxng_pref_list())
        self.lock(get_setting("preferences.lock", []))
        for pref in self.components.values():
            if isinstance(pref, (EngineMapPrefs, Categories)):
                pref.init(self)

    @property
    def disabled_engines(self) -> list[str]:
        grp: EngineMapPrefs = self.components["engines"]  # type: ignore
        return grp.disabled_engines

    def process_request(self, client: "searx.client.HTTPClient"):

        try:
            self.parse_cookies(sxng_request)
        except Exception as exc:  # pylint: disable=broad-except
            log.exception(exc, exc_info=True)
            sxng_request.errors.append(lazy_gettext("Invalid settings, please edit your preferences"))

        if sxng_request.form.get("pref_url_params"):
            self.parse_encoded_data(sxng_request.form["pref_url_params"])
        else:
            try:
                self.parse_form(sxng_request.form)
            except Exception as exc:  # pylint: disable=broad-except
                log.exception(exc, exc_info=True)
                sxng_request.errors.append(lazy_gettext("Invalid settings"))

        if not self.value("search_locale_tag"):

            # If search language is defined neither in settings nor in
            # preferences use the browser Accept-Language header.
            tag = searx.locales.sxng_locale_tag(client.locale)

            # Find best match in the configured search languages/regions. Best
            # match from the catalog of search languages in the preferences.
            search_locale: SingleChoice = self.components["search_locale_tag"]  # type: ignore
            tag = searx.locales.match_locale(tag, search_locale.str2obj.keys())

            if tag:
                search_locale.set(tag)
                log.debug('set search_locale_tag %s (from browser)', tag)

        if not self.value("ui_locale_tag"):

            # If UI locale is defined neither in settings nor in preferences use
            # the browser Accept-Language header.
            tag = searx.locales.language_tag(client.locale)

            # Find best match in the configured search languages/regions. Best
            # match from the catalog of search languages in the preferences.

            ui_locale: SingleChoice = self.components["ui_locale_tag"]  # type: ignore
            tag = searx.locales.match_locale(tag, ui_locale.str2obj.keys())
            if tag:
                ui_locale.set(tag)
                log.debug('set ui_locale_tag %s (from browser)', tag)

        # Browser quirks ..
        #
        # - https://github.com/searx/searx/pull/2132
        # - https://github.com/searx/searx/issues/1666
        user_agent = sxng_request.headers.get("User-Agent", "").lower()
        if "webkit" in user_agent and "android" in user_agent:
            http_method: SingleChoice = self.components["method"]  # type: ignore
            http_method.set("GET")
            http_method.lock()

    def validate_token(self, engine: Engine | types.ModuleType) -> bool:
        if not getattr(engine, "tokens", None):
            return True

        token_list = [t.strip() for t in self.value("tokens").split(",")]
        valid = False
        for eng_token in engine.tokens:
            if eng_token in token_list:
                valid = True
                break
        return valid

    @property
    def req_plugins(self) -> list[str]:
        """Returns the list of plugin IDs of the activated plugins."""
        grp: BoolGrp = self.components["plugins"]  # type: ignore
        return [plg_id for plg_id, _val in grp.members.items() if _val]
