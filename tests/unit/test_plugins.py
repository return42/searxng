# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,disable=missing-class-docstring,invalid-name

import babel
from flask_babel import lazy_gettext
from mock import Mock

import searx
import searx.plugins
import searx.preferences
import searx.results

from searx.result_types import Result
from searx.extended_types import sxng_request

from tests import SearxTestCase

plg_store = searx.plugins.Storage()
plg_store.load_settings(searx.get_setting("plugins"))


def get_search_mock(query, **kwargs):

    lang = kwargs.get("lang", "en-US")
    kwargs["pageno"] = kwargs.get("pageno", 1)
    kwargs["locale"] = babel.Locale.parse(lang, sep="-")
    user_plugins = kwargs.pop("user_plugins", [x.id for x in plg_store])

    return Mock(
        search_query=Mock(query=query, **kwargs),
        user_plugins=user_plugins,
        result_container=searx.results.ResultContainer(),
    )


def do_pre_search(query, storage, **kwargs) -> bool:

    search = get_search_mock(query, **kwargs)
    ret = storage.pre_search(sxng_request, search)
    return ret


def do_post_search(query, storage, **kwargs) -> Mock:

    search = get_search_mock(query, **kwargs)
    storage.post_search(sxng_request, search)
    return search


class PluginMock(searx.plugins.Plugin):

    def __init__(self, plg_id: str, plg_name: str, plg_active: bool):

        class Info(searx.plugins.PluginInfo):
            name = lazy_gettext(plg_name)
            preference_section = "general"
            description = lazy_gettext(f"Dummy plugin: {plg_id}")

        class Cfg(searx.plugins.PluginCfg):
            int_cfg: int
            str_cfg: str

        self.id = plg_id
        self.info_factory = Info  # pyright: ignore[reportAttributeAccessIssue]
        self.cfg_factory = Cfg  # pyright: ignore[reportAttributeAccessIssue]

        plg_cfg = searx.plugins.StoragePlgCfg(
            active=plg_active,
            cfg={"int_cfg": "42", "str_cfg": "lorem"},
        )
        super().__init__(plg_cfg)

    # pylint: disable= unused-argument
    def pre_search(self, request, search) -> bool:
        return True

    def post_search(self, request, search) -> None:
        return None

    def on_result(self, request, search, result) -> bool:
        return False


class PluginStorage(SearxTestCase):

    def setUp(self):
        super().setUp()
        engines = {}

        self.storage = searx.plugins.Storage()
        self.storage.register(PluginMock("plg001", "first plugin", True))
        self.storage.register(PluginMock("plg002", "second plugin", True))
        self.storage.init_from_app(self.app)
        self.pref = searx.preferences.Preferences(["simple"], ["general"], engines, self.storage)
        self.pref.load_dict({"locale": "en"})

    def test_init(self):

        self.assertEqual(2, len(self.storage))

    def test_hooks(self):

        with self.app.test_request_context():
            sxng_request.preferences = self.pref
            query = ""

            ret = do_pre_search(query, self.storage, pageno=1)
            self.assertTrue(ret is True)

            ret = self.storage.on_result(
                sxng_request,
                get_search_mock("lorem ipsum", user_plugins=["plg001", "plg002"]),
                Result(),
            )
            self.assertFalse(ret)
