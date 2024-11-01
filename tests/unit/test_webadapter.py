# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

from searx.preferences import Preferences
import searx.engines
import searx.search
from searx.search import EngineRef
from searx.webadapter import validate_engineref_list
from tests import SearxTestCase


PRIVATE_ENGINE_NAME = 'general private offline'
TEST_ENGINES = [
    {
        'name': PRIVATE_ENGINE_NAME,
        'engine': 'dummy-offline',
        'categories': 'general',
        'shortcut': 'do',
        'timeout': 3.0,
        'tokens': ['my-token'],
    },
]
SEARCHQUERY = [EngineRef(PRIVATE_ENGINE_NAME, 'general')]


class ValidateQueryCase(SearxTestCase):  # pylint: disable=missing-class-docstring
    @classmethod
    def setUpClass(cls):
        searx.search.initialize(TEST_ENGINES)

    def test_query_private_engine_without_token(self):  # pylint:disable=invalid-name
        preferences = Preferences(['simple'], ['general'], searx.engines.ENGINE_MAP, [])
        valid, unknown, invalid_token = validate_engineref_list(SEARCHQUERY, preferences)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(unknown), 0)
        self.assertEqual(len(invalid_token), 1)

    def test_query_private_engine_with_incorrect_token(self):  # pylint:disable=invalid-name
        preferences_with_tokens = Preferences(['simple'], ['general'], searx.engines.ENGINE_MAP, [])
        preferences_with_tokens.parse_dict({'tokens': 'bad-token'})
        valid, unknown, invalid_token = validate_engineref_list(SEARCHQUERY, preferences_with_tokens)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(unknown), 0)
        self.assertEqual(len(invalid_token), 1)

    def test_query_private_engine_with_correct_token(self):  # pylint:disable=invalid-name
        preferences_with_tokens = Preferences(['simple'], ['general'], searx.engines.ENGINE_MAP, [])
        preferences_with_tokens.parse_dict({'tokens': 'my-token'})
        valid, unknown, invalid_token = validate_engineref_list(SEARCHQUERY, preferences_with_tokens)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(unknown), 0)
        self.assertEqual(len(invalid_token), 0)
