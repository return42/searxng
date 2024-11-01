# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

from mock import Mock
from parameterized import parameterized

import searx.answerers
from tests import SearxTestCase


class AnswererTest(SearxTestCase):  # pylint: disable=missing-class-docstring
    @parameterized.expand(searx.answerers.ANSWERERS_MAP)
    def test_unicode_input(self, answerer):
        query = Mock()
        unicode_payload = 'árvíztűrő tükörfúrógép'
        query.query = '{} {}'.format(answerer.keywords[0], unicode_payload)
        self.assertIsInstance(answerer.answer(query), list)
