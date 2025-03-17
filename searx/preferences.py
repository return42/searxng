# SPDX-License-Identifier: AGPL-3.0-or-later
"""Implementation of SearXNG's preferences.
"""
from __future__ import annotations
import typing

import types
from dataclasses import dataclass
from flask_babel import lazy_gettext

import searx.engines
import searx.locales
import searx.plugins

from searx.extended_types import sxng_request
from searx import logger, get_setting, autocomplete, favicons
from searx.enginelib import Engine
from searx.engines import DEFAULT_CATEGORY

from .components import Form, Field, SingleChoice, Bool, BoolGrp, FieldCollection
from .components.filters import SafeSearch, CategoriesAsTabs, SearchLocale
from .settings_defaults import get_typedef

if typing.TYPE_CHECKING:
    import searx.client

log = logger.getChild("preferences")


class PluginStoragePrefs(BoolGrp):
    """The preferences for the plugins are feed from the :py:obj:`PluginStorage
    <searx.plugins.PluginStorage>`, the ``member_name`` of a plugin is the
    :py:obj:`Plugin.id <searx.plugins.Plugin.id>` of the plugin.
    """

    bool2str = {True: "on", False: "off"}

    def __init__(self, plg_storage: searx.plugins.PluginStorage):

        grp_id = "plugins"
        members: dict[str, Bool] = {}

        for plg in plg_storage:
            field_name = self.sep.join([grp_id, plg.id])
            field = Bool(
                name=field_name,
                default=self.bool2str[plg.active],
                bool2str=self.bool2str,
            )
            field.form_id = self.form_id
            members[plg.id] = field

        super().__init__(form_id="prefs", grp_id=grp_id, members=members)

    @property
    def req_plugins(self) -> list[str]:
        """List of IDs of the activated plugins."""
        return [plg_id for plg_id, _val in self.members.items() if _val.value]


class EngineMapPrefs(BoolGrp):
    """Engine preferences are similar to a :py:obj:`BooleanGroup`, but the special
    thing about these preferences is that an engine can be switched "on" within one
    category and "off" in another category.  The context of the categories is
    made up of the categories that are also configured as tabs (:ref:`settings
    categories_as_tabs`).
    """

    categories: dict[str, list[Bool]]
    """Categories and the engines (on/off) contained therein.  An engine can be
    assigned to several categories and there are categories that are displayed
    as tabs and other categories that (only) represent sub-groupings.

    The categories displayed as tabs are a subgroup of the categories stored
    here.
    """

    bool2str = {True: "on", False: "off"}

    def __init__(self, engines: list[Engine | types.ModuleType]):
        super().__init__(form_id="prefs", grp_id="engines", members={})
        self._engines = engines
        self.categories = {}

    def init(self, prefs: Preferences):
        """Member (engines) of this group, sorted into the categories."""

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
                    default=self.bool2str[not eng.disabled],
                    bool2str=self.bool2str,
                )
                self.members[eng.name] = field
                self.categories[eng_categ].append(field)

        # sort the engines alphabetically since the order in settings.yml is meaningless.
        for l in self.categories.values():
            l.sort(key=lambda b: b.name)

        # ref to engines is no longer needed
        self._engines = []

    @property
    def disabled_engines(self) -> list[str]:
        return [eng_name for eng_name, field in self.members.items() if not field.value]


@dataclass
class PrefFields(FieldCollection):
    """Type definition of the fields used in preferences."""

    engines: EngineMapPrefs
    plugins: PluginStoragePrefs
    autocomplete: SingleChoice
    categories_as_tabs: CategoriesAsTabs
    center_alignment: Bool
    doi_resolver: SingleChoice
    favicon_resolver: SingleChoice
    hotkeys: SingleChoice
    image_proxy: Bool
    infinite_scroll: Bool
    search_locale_tag: SearchLocale
    ui_locale_tag: SingleChoice
    method: SingleChoice
    query_in_title: Bool
    results_on_new_tab: Bool
    safesearch: SafeSearch
    search_on_category_select: Bool
    theme: SingleChoice
    simple_style: SingleChoice
    url_formatting: SingleChoice
    tokens: Field

    @staticmethod
    def build() -> PrefFields:
        return PrefFields(
            engines=EngineMapPrefs(list(searx.engines.engines.values())),
            plugins=PluginStoragePrefs(searx.plugins.STORAGE),
            autocomplete=SingleChoice(
                name="autocomplete",
                default=get_setting("search.autocomplete") or "-",
                catalog={"-": None} | autocomplete.backends,
                legend=lazy_gettext("Autocomplete"),
                description=lazy_gettext("Find stuff as you type"),
            ),
            categories_as_tabs=CategoriesAsTabs(
                name="categories",
                default=["general"],
                catalog={"general"} | set(get_setting("categories_as_tabs").keys()),
            ),
            center_alignment=Bool(
                name="center_alignment",
                default=Bool.bool2str[get_setting("ui.center_alignment")],
                legend=lazy_gettext("Center Alignment"),
                description=lazy_gettext("Displays results in the center of the page."),
            ),
            doi_resolver=SingleChoice(
                name="doi_resolver",
                default=get_setting("default_doi_resolver"),
                catalog=get_setting("doi_resolvers").keys(),
                legend=lazy_gettext("Open Access DOI resolver"),
                description=lazy_gettext("Select service used by DOI rewrite"),
            ),
            favicon_resolver=SingleChoice(
                name="favicon_resolver",
                default=get_setting("search.favicon_resolver") or "-",
                catalog={"-": None} | favicons.proxy.CFG.resolver_map,
                legend=lazy_gettext("Favicon Resolver"),
                description=lazy_gettext("Display favicons near search results"),
            ),
            hotkeys=SingleChoice(
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
            image_proxy=Bool(
                name="image_proxy",
                default=Bool.bool2str[get_setting("server.image_proxy")],
                legend=lazy_gettext("Image proxy"),
                description=lazy_gettext("Proxying image results through SearXNG"),
            ),
            infinite_scroll=Bool(
                name="infinite_scroll",
                default=Bool.bool2str[get_setting("ui.infinite_scroll")],
                legend=lazy_gettext("Infinite scroll"),
                description=lazy_gettext("Automatically load next page when scrolling to bottom of current page"),
            ),
            search_locale_tag=SearchLocale(
                name="search_locale_tag",  # FIXME old name was "language"
                legend=lazy_gettext("Search language"),
                description=(
                    lazy_gettext("What language do you prefer for search?")
                    + lazy_gettext("Choose Auto-detect to let SearXNG detect the language of your query.")
                ),
            ),
            ui_locale_tag=SingleChoice(
                name="ui_locale_tag",  # FIXME old name was "locale"
                default=sxng_request.client.ui_locale_tag,
                legend=lazy_gettext("Interface language"),
                description=lazy_gettext("Change the language of the layout"),
                catalog=set(searx.locales.LOCALE_NAMES.keys()),
                catalog_descr=searx.locales.LOCALE_NAMES,
            ),
            method=SingleChoice(
                name="method",
                default=get_setting("server.method"),
                catalog=get_typedef("server.method"),
                legend=lazy_gettext("HTTP Method"),
                description=lazy_gettext("Change how forms are submitted"),
            ),
            query_in_title=Bool(
                name="query_in_title",
                default=Bool.bool2str[get_setting("ui.query_in_title")],
                legend=lazy_gettext("Query in the page's title"),
                description=lazy_gettext(
                    "When enabled, the result page's title contains your query. Your browser can record this title"
                ),
            ),
            results_on_new_tab=Bool(
                name="results_on_new_tab",
                default=Bool.bool2str[get_setting("ui.results_on_new_tab")],
                legend=lazy_gettext("Results on new tabs"),
                description=lazy_gettext("Open result links on new browser tabs"),
            ),
            safesearch=SafeSearch(name="safesearch", default=get_setting("server.safe_search")),
            search_on_category_select=Bool(
                name="search_on_category_select",
                default=Bool.bool2str[get_setting("ui.search_on_category_select")],
                legend=lazy_gettext("Search on category select"),
                description=lazy_gettext(
                    "Perform search immediately if a category selected. Disable to select multiple categories."
                ),
            ),
            theme=SingleChoice(
                name="theme",
                default=get_setting("ui.default_theme"),
                catalog=get_typedef("ui.default_theme"),
                legend=lazy_gettext("Theme"),
                description=lazy_gettext("Change SearXNG layout"),
            ),
            simple_style=SingleChoice(
                name="simple_style",
                default=get_setting("ui.theme_args.simple_style"),
                catalog=get_typedef("ui.theme_args.simple_style"),
                legend=lazy_gettext("Theme style"),
                description=lazy_gettext("Choose auto to follow your browser settings"),
            ),
            url_formatting=SingleChoice(
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
            tokens=Field(
                name="tokens",
                default="",
                legend=lazy_gettext("Engine tokens"),
                description=lazy_gettext("Access tokens for private engines"),
            ),
        )


class Preferences(Form):
    """Form fields of the preferences."""

    fields: PrefFields

    def __init__(self):
        super().__init__(form_id="prefs", fields=PrefFields.build(), cookie_name="sxng_prefs")
        # first init engines in categories
        self.fields.engines.init(self)
        # after init categories to remove categories with non engine in
        self.fields.categories_as_tabs.init()

    def validate_token(self, engine: Engine | types.ModuleType) -> bool:
        if not self.fields.tokens:
            return True

        token_list = [t.strip() for t in self.fields.tokens.value.split(",")]
        valid = False
        for eng_token in engine.tokens:
            if eng_token in token_list:
                valid = True
                break
        return valid

    def process_request(self):

        try:
            self.parse_cookies(sxng_request)
        except Exception as exc:  # pylint: disable=broad-except
            log.exception(exc, exc_info=True)
            sxng_request.errors.append(lazy_gettext("Invalid settings, please edit your preferences"))

        if sxng_request.form.get("pref_url_params"):
            self.load_b64encode(sxng_request.form["pref_url_params"])
        else:
            try:
                self.parse_request()
            except Exception as exc:  # pylint: disable=broad-except
                log.exception(exc, exc_info=True)
                sxng_request.errors.append(lazy_gettext("Invalid settings"))

        # set search language from client
        self.fields.search_locale_tag.set(sxng_request.client.search_locale_tag)

        # set UI language from client
        self.fields.ui_locale_tag.set(sxng_request.client.ui_locale_tag)

        # Browser quirks ..
        #
        # - https://github.com/searx/searx/pull/2132
        # - https://github.com/searx/searx/issues/1666
        user_agent = sxng_request.headers.get("User-Agent", "").lower()
        if "webkit" in user_agent and "android" in user_agent:
            http_method: SingleChoice = self.components["method"]  # type: ignore
            http_method.set("GET")
            http_method.lock()
