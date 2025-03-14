# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,disable=missing-class-docstring,invalid-name

from searx import settings, engines
from tests import SearxTestCase


class TestEnginesInit(SearxTestCase):

    def test_initialize_engines_default(self):
        engine_list = [
            {'engine': 'dummy', 'name': 'engine1', 'shortcut': 'e1'},
            {'engine': 'dummy', 'name': 'engine2', 'shortcut': 'e2'},
        ]

        engines.load_engines(engine_list)
        self.assertEqual(len(engines.engines), 2)
        self.assertIn('engine1', engines.engines)
        self.assertIn('engine2', engines.engines)

    def test_initialize_engines_exclude_onions(self):
        settings['outgoing']['using_tor_proxy'] = False
        engine_list = [
            {'engine': 'dummy', 'name': 'engine1', 'shortcut': 'e1', 'categories': 'general'},
            {'engine': 'dummy', 'name': 'engine2', 'shortcut': 'e2', 'categories': 'onions'},
        ]

        engines.load_engines(engine_list)
        self.assertEqual(len(engines.engines), 1)
        self.assertIn('engine1', engines.engines)
        self.assertNotIn('onions', engines.categories)

    def test_initialize_engines_include_onions(self):
        settings['outgoing']['using_tor_proxy'] = True
        settings['outgoing']['extra_proxy_timeout'] = 100.0
        engine_list = [
            {
                'engine': 'dummy',
                'name': 'engine1',
                'shortcut': 'e1',
                'categories': 'general',
                'timeout': 20.0,
                'onion_url': 'http://engine1.onion',
            },
            {'engine': 'dummy', 'name': 'engine2', 'shortcut': 'e2', 'categories': 'onions'},
        ]

        engines.load_engines(engine_list)
        self.assertEqual(len(engines.engines), 2)
        self.assertIn('engine1', engines.engines)
        self.assertIn('engine2', engines.engines)
        self.assertIn('onions', engines.categories)
        self.assertIn('http://engine1.onion', engines.engines['engine1'].search_url)
        self.assertEqual(engines.engines['engine1'].timeout, 120.0)

    def test_missing_name_field(self):
        settings['outgoing']['using_tor_proxy'] = False
        engine_list = [
            {'engine': 'dummy', 'shortcut': 'e1', 'categories': 'general'},
        ]
        with self.assertLogs('searx.engines', level='ERROR') as cm:  # pylint: disable=invalid-name
            engines.load_engines(engine_list)
            self.assertEqual(len(engines.engines), 0)
            self.assertEqual(cm.output, ['ERROR:searx.engines:An engine does not have a "name" field'])

    def test_missing_engine_field(self):
        settings['outgoing']['using_tor_proxy'] = False
        engine_list = [
            {'name': 'engine2', 'shortcut': 'e2', 'categories': 'onions'},
        ]
        with self.assertLogs('searx.engines', level='ERROR') as cm:  # pylint: disable=invalid-name
            engines.load_engines(engine_list)
            self.assertEqual(len(engines.engines), 0)
            self.assertEqual(
                cm.output, ['ERROR:searx.engines:The "engine" field is missing for the engine named "engine2"']
            )
