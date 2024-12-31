# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

import pathlib
import os

# Before import from the searx package, we need to set up the (debug)
# environment.  The import of the searx package initialize the searx.settings
# and this in turn takes the defaults from the environment!
#
# pylint: disable=wrong-import-position

os.environ.pop('SEARXNG_SETTINGS_PATH', None)
os.environ['SEARXNG_DEBUG'] = '1'
os.environ['SEARXNG_DEBUG_LOG_LEVEL'] = 'WARNING'
os.environ['SEARXNG_DISABLE_ETC_SETTINGS'] = '1'

import aiounittest
import searx

test_settings_folder = pathlib.Path(__file__).parent / "unit" / "settings"


class SearxTestLayer:
    """Base layer for non-robot tests."""

    __name__ = 'SearxTestLayer'

    @classmethod
    def setUp(cls):
        pass

    @classmethod
    def tearDown(cls):
        pass

    @classmethod
    def testSetUp(cls):
        pass

    @classmethod
    def testTearDown(cls):
        pass


class SearxTestCase(aiounittest.AsyncTestCase):
    """Base test case for non-robot tests."""

    layer = SearxTestLayer

    def setattr4test(self, obj, attr, value):
        """setattr(obj, attr, value) but reset to the previous value in the
        cleanup."""
        previous_value = getattr(obj, attr)

        def cleanup_patch():
            setattr(obj, attr, previous_value)

        self.addCleanup(cleanup_patch)
        setattr(obj, attr, value)

    def init_test_settings(self, cfg_fname: str = "test_settings.yml"):
        """Sets ``SEARXNG_SETTINGS_PATH`` environment variable an initialize
        global ``settings`` variable and ``logger`` from a test config in
        :origin:`tests/unit/settings/`.
        """

        os.environ['SEARXNG_SETTINGS_PATH'] = str(test_settings_folder/cfg_fname)
        searx.init_settings()
