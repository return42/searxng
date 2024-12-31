# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring, disable=missing-class-docstring

from parameterized import parameterized
import searx.answerers
from tests import SearxTestCase


class AnswererTest(SearxTestCase):

    def setUp(self):
        self.init_test_settings()

    @parameterized.expand(searx.answerers.STORAGE.answerer_list)
    def test_unicode_input(self, answerer_obj: searx.answerers.Answerer):
        unicode_payload = "árvíztűrő tükörfúrógép"

        for keyword in answerer_obj.keywords:
            query = f"{keyword} {unicode_payload}"
            self.assertIsInstance(answerer_obj.answer(query), list)
