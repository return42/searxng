# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, invalid-name
from parameterized.parameterized import parameterized

import flask
from flask_babel import gettext

import searx.plugins
import searx.preferences
import searx.limiter
import searx.botdetection

from searx.result_types import Answer
from searx.utils import load_module

from tests import SearxTestCase
from .test_plugins import do_post_search


class PluginIPSelfInfo(SearxTestCase):  # pylint: disable=missing-class-docstring

    def setUp(self):
        self.init_test_settings()
        # pylint: disable=import-outside-toplevel
        from searx.webapp import app
        from searx.plugins._core import _default, ModulePlugin

        f = _default / "self_info.py"
        mod = load_module(f.name, str(f.parent))
        engines = {}

        self.app = app
        self.storage = searx.plugins.PluginStorage()
        self.storage.register(ModulePlugin(mod))
        self.storage.init(self.app)
        self.pref = searx.preferences.Preferences(["simple"], ["general"], engines, self.storage)
        self.pref.parse_dict({"locale": "en"})
        cfg = searx.limiter.get_cfg()
        searx.botdetection.init(cfg, None)

    def test_plugin_store_init(self):
        self.assertEqual(1, len(self.storage))

    def test_pageno_1_2(self):
        with self.app.test_request_context():
            flask.request.preferences = self.pref
            flask.request.remote_addr = "127.0.0.1"
            flask.request.headers = {"X-Forwarded-For": "1.2.3.4, 127.0.0.1", "X-Real-IP": "127.0.0.1"}
            answer = Answer(results=[], answer=gettext("Your IP is: ") + "127.0.0.1")

            search = do_post_search("ip", self.storage, pageno=1)
            self.assertIn(answer, search.result_container.answers)

            search = do_post_search("ip", self.storage, pageno=2)
            self.assertEqual(search.result_container.answers, [])

    @parameterized.expand(
        [
            'user-agent',
            'What is my User-Agent?',
        ]
    )
    def test_user_agent_in_answer(self, query: str):
        with self.app.test_request_context():
            flask.request.preferences = self.pref
            flask.request.user_agent = "Dummy agent"
            answer = Answer(results=[], answer=gettext("Your user-agent is: ") + "Dummy agent")

            search = do_post_search(query, self.storage, pageno=1)
            self.assertIn(answer, search.result_container.answers)

            search = do_post_search("ip", self.storage, pageno=2)
            self.assertEqual(search.result_container.answers, [])
