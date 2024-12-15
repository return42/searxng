# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, missing-class-docstring, too-few-public-methods

import babel
import flask
from mock import Mock

import searx.plugins
import searx.preferences
from tests import SearxTestCase


def get_search_mock(query, **kwargs):
    lang = kwargs.get("lang", "en-US")
    kwargs["pageno"] = kwargs.get("pageno", 1)
    kwargs["locale"] = babel.Locale.parse(lang, sep="-")
    return Mock(search_query=Mock(query=query, **kwargs), result_container=Mock(answers={}))


def do_post_search(query, storage, **kwargs):
    search = get_search_mock(query, **kwargs)
    storage.post_search(flask.request, search)
    return search


class PluginMock(searx.plugins.Plugin):
    """Dummy Plugin"""

    def __init__(self, _id: str, name: str, default_on: bool):
        self.id = _id
        self.default_on = default_on
        self._name = name
        super().__init__()

    def pre_search(self, _request, _searchs):
        return True

    def post_search(self, _request, _searchs) -> None:
        return None

    def on_result(self, _request, _search, _result) -> bool:
        return False

    def info(self):
        return searx.plugins.PluginInfo(
            id=self.id,
            name=self._name,
            description=f"Dummy plugin: {self.id}",
            preference_section="general",
        )


class PluginStoreTest(SearxTestCase):  # pylint: disable=missing-class-docstring

    def setUp(self):
        # pylint: disable=import-outside-toplevel
        from searx.webapp import app
        engines = {}

        self.app = app
        self.storage = searx.plugins.PluginStorage()
        self.storage.register(PluginMock("plg001", "first plugin", True))
        self.storage.register(PluginMock("plg002", "second plugin", True))
        self.storage.init(self.app)
        self.pref = searx.preferences.Preferences(["simple"], ["general"], engines, self.storage)
        self.pref.parse_dict({"locale": "en"})

    def test_init(self):

        self.assertEqual(2, len(self.storage))

    def test_hooks(self):

        ret = self.storage.pre_search(None, None)  # type: ignore
        self.assertTrue(ret)

        self.storage.post_search(None, None)  # type: ignore

        ret = self.storage.on_result(None, None, None)  # type: ignore
        self.assertFalse(ret)
