# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,disable=missing-class-docstring,invalid-name

from parameterized import parameterized

import searx.answerers
import searx.preferences

from searx.extended_types import sxng_request

from tests import SearxTestCase


class AnswererTest(SearxTestCase):

    def setUp(self):
        super().setUp()

        self.pref = searx.preferences.Preferences()
        self.pref.components["loaclae"].parse_form({"locale": "en"})

    @parameterized.expand(searx.answerers.STORAGE.answerer_list)
    def test_unicode_input(self, answerer_obj: searx.answerers.Answerer):

        with self.app.test_request_context():
            sxng_request.preferences = self.pref

            unicode_payload = "árvíztűrő tükörfúrógép"
            for keyword in answerer_obj.keywords:
                query = f"{keyword} {unicode_payload}"
                self.assertIsInstance(answerer_obj.answer(query), list)
