# SPDX-License-Identifier: AGPL-3.0-or-later
"""Implementation of SearXNG's preferences.
"""
from __future__ import annotations

import typing

from flask_babel import gettext

import searx.client
import searx.engines
import searx.locales
import searx.plugins

from searx.extended_types import sxng_request
from searx import logger, get_setting, autocomplete, favicons
from searx.enginelib import Engine
from searx.engines import DEFAULT_CATEGORY

from .components import Form, FieldABC, Field, SingleChoice, Bool, MultipleChoice, BoolGrp
from .settings_defaults import get_typedef

logger = logger.getChild("preferences")


class PluginStoragePrefs(BoolGrp):
    """The preferences for the plugins are feed from the :py:obj:`PluginStorage
    <searx.plugins.PluginStorage>`, the ``member_name`` of a plugin is the
    :py:obj:`Plugin.id <searx.plugins.Plugin.id>` of the plugin.
    """

    def __init__(self, form_id: str, grp_name: str, plg_storage: searx.plugins.PluginStorage):
        super().__init__(form_id, grp_name)

        for plg in plg_storage:
            field_name = self.sep.join([self.grp_name, plg.id])
            field = Bool(name=field_name, default=plg.active)
            field.form_id = self.form_id
            self.members[plg.id] = field


class EngineMapPrefs(BoolGrp):
    """Engine preferences are similar to a :py:obj:`BooleanGroup`, but the special
    thing about these preferences is that an engine can be switched "on" within one
    category and "off" in another category.  The context of the categories is
    made up of the categories that are also configured as tabs (:ref:`settings
    categories_as_tabs`).
    """

    categories = dict[str, list[Bool]]
    """Members of this group sorted by category name."""

    def __init__(self, form_id: str, grp_name: str, engines: list[Engine]):
        super().__init__(form_id, grp_name)

        self.categories = {}
        categs: set = {DEFAULT_CATEGORY}
        categs.update(get_setting("categories_as_tabs", {}).keys())  # type: ignore

        # build members by adding the category context and the name of the
        # engine to the field name.

        for eng in engines:
            for eng_categ in eng.categories:
                if eng_categ not in categs:
                    continue
                if eng_categ not in self.categories:
                    self.categories[eng_categ] = []

                # hint: the engine name may contain spaces, but the ID of HTML
                # element (e.g. <input id="...">) must not contain whitespaces!
                field_name = self.sep.join([eng_categ.replace(' ', '_'), eng.name.replace(' ', '_')])
                field = Bool(name=field_name, default=bool(not eng.disabled))
                self.members[eng.name] = field
                self.categories[eng_categ] = field

    @property
    def disabled_engines(self) -> list[str]:
        return [ eng_name for eng_name, field in self.members.items() if not field.value ]

def sxng_pref_list() -> list[FieldABC | BoolGrp]:
    return [
        PluginStoragePrefs("pref", "plugins", searx.plugins.STORAGE),
        EngineMapPrefs("pref", "engines", searx.engines.engines),  # type: ignore
        SingleChoice(
            name="autocomplete",
            default=get_setting("search.autocomplete"),
            catalog={"-": None} | autocomplete.backends.keys(),
        ),
        MultipleChoice(
            name="categories",
            default={"general"},
            catalog={"general"} | set(get_setting("categories_as_tabs").keys()),
        ),
        Bool(
            name="center_alignment",
            default=get_setting("ui.center_alignment"),
        ),
        SingleChoice(
            name="doi_resolver", default=get_setting("default_doi_resolver"), catalog=get_setting("doi_resolvers")
        ),
        SingleChoice(
            name="favicon_resolver",
            default=get_setting("search.favicon_resolver"),
            catalog={"-": None} | favicons.proxy.CFG.resolver_map,
        ),
        SingleChoice(
            name="hotkeys",
            default=get_setting("ui.hotkeys"),
            catalog=get_typedef("ui.hotkeys"),
        ),
        Bool(name="image_proxy", default=get_setting("server.image_proxy")),
        Bool(
            name="infinite_scroll",
            default=get_setting("ui.infinite_scroll"),
        ),
        SingleChoice(
            name="search_locale_tag",  # FIXME old name was "language"
            default=get_setting("search.default_lang"),
            catalog=[""] + get_setting("search.languages"),
        ),
        SingleChoice(
            name="ui_locale_tag",  # FIXME old name was "locale"
            default=get_setting("ui.default_locale"),
            catalog=[""] + list(searx.locales.LOCALE_NAMES.keys()),
        ),
        SingleChoice(
            name="method",
            default=get_setting("server.method"),
            catalog=get_typedef("server.method"),
        ),
        Bool(
            name="query_in_title",
            default=get_setting("ui.query_in_title"),
        ),
        Bool(
            name="results_on_new_tab",
            default=get_setting("ui.results_on_new_tab"),
        ),
        SingleChoice(
            name="safesearch",
            default=get_setting("server.safe_search"),
            catalog=get_typedef("server.safe_search"),
        ),
        Bool(
            name="search_on_category_select",
            default=get_setting("ui.search_on_category_select"),
        ),
        SingleChoice(
            name="theme",
            default=get_setting("ui.default_theme"),
            catalog=get_typedef("ui.default_theme"),
        ),
        SingleChoice(
            name="simple_style",
            default=get_setting("ui.theme_args.simple_style"),
            catalog=get_typedef("ui.theme_args.simple_style"),
        ),
        SingleChoice(
            name="url_formatting",
            default=get_setting("ui.url_formatting"),
            catalog=get_typedef("ui.url_formatting"),
        ),
        Field(
            name="tokens",
            default="",
        ),
    ]


class Preferences(Form):
    """A collection of prefernces."""

    def __init__(self):
        super().__init__("pref", sxng_pref_list())
        self.lock(get_setting("preferences.lock", []))

    @property
    def disabled_engines(self) -> list[str]:
        grp: EngineMapPrefs = self.components["engines"] # type: ignore
        return grp.disabled_engines

    def process_request(self, client: searx.client.HTTPClient):

        try:
            self.parse_cookies(sxng_request.cookies)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception(exc, exc_info=True)
            sxng_request.errors.append(gettext("Invalid settings, please edit your preferences"))

        if sxng_request.form.get("pref_url_params"):
            self.parse_encoded_data(sxng_request.form["pref_url_params"])
        else:
            try:
                self.parse_form(sxng_request.form)
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception(exc, exc_info=True)
                sxng_request.errors.append(gettext("Invalid settings"))

        if not self.value("search_locale_tag"):

            # If search language is defined neither in settings nor in
            # preferences use the browser Accept-Language header.
            tag = searx.locales.sxng_tag(client.locale)

            # Find best match in the configured search languages/regions. Best
            # match from the catalog of search languages in the preferences.
            search_locale: SingleChoice = self.components["search_locale_tag"]  # type: ignore
            tag = searx.locales.match_locale(tag, search_locale.catalog)

            if tag:
                search_locale.set(tag)
                logger.debug('set search_locale_tag %s (from browser)', tag)

        if not self.value("ui_locale_tag"):

            # If UI locale is defined neither in settings nor in preferences use
            # the browser Accept-Language header.
            tag = searx.locales.language_tag(client.locale)

            # Find best match in the configured search languages/regions. Best
            # match from the catalog of search languages in the preferences.

            ui_locale: SingleChoice = self.components["ui_locale_tag"]  # type: ignore
            tag = searx.locales.match_locale(tag, ui_locale.catalog)
            if tag:
                ui_locale.set(tag)
                logger.debug('set ui_locale_tag %s (from browser)', tag)

        # Browser quirks ..
        #
        # - https://github.com/searx/searx/pull/2132
        # - https://github.com/searx/searx/issues/1666
        user_agent = sxng_request.headers.get("User-Agent", "").lower()
        if "webkit" in user_agent and "android" in user_agent:
            http_method: SingleChoice = self.components["method"]  # type: ignore
            http_method.set("GET")
            http_method.lock()

    def validate_token(self, engine) -> bool:
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
        return [ plg_id for plg_id, _val in grp.members.items() if _val]
