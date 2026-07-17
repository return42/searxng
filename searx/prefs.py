# SPDX-License-Identifier: AGPL-3.0-or-later
"""Basic implementation for preferences."""

import typing as t

from collections import abc as c_abc
import msgspec
import flask
from werkzeug.datastructures import ImmutableMultiDict

from . import forms


class SettingsPref(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    """Options for configuring the preferences

    .. code:: yaml

       preferences:
         lock:
           - favicon_resolver
           - image_proxy
           - method
       # ...

    """

    lock: set[
        t.Literal[
            "autocomplete",
            "categories",
            "center_alignment",
            "favicon_resolver",
            "image_proxy",
            "language",
            "locale",
            "method",
            "query_in_title",
            "results_on_new_tab",
            "safesearch",
            "search_on_category_select",
            "simple_style",
            "theme",
        ]
    ] = set()
    """Lock arbitrary settings on the preferences page."""


class Pref(forms.Field[forms.ValT], t.Generic[forms.ValT]):
    """Base class for preferences."""
    pass


class OnOffGroup(forms.OnOffGroup):
    """Base class for groups of on/off preferences """
    pass


PrefType: t.TypeAlias = Pref[t.Any] | OnOffGroup


class PrefStorage:
    """A storage for managing the *preferences* of SearXNG."""

    def __init__(self):
        self._by_id: dict[str, PrefType] = {}

    def __iter__(self) -> c_abc.Generator[PrefType]:
        yield from self._by_id.values()

    def __len__(self):
        return len(self._by_id)

    def get(self, pref_id: str) -> PrefType | None:
        return self._by_id.get(pref_id)

    def register(self, pref_list: PrefType | c_abc.Sequence[PrefType]):
        """Register preference objects.  In case of name collision (if two
        preferences have same ID) a :obj:`KeyError` exception is raised.
        """
        if not isinstance(pref_list, c_abc.Sequence):
            pref_list = [pref_list]
        for pref in pref_list:
            if self.get(pref.id):
                raise KeyError(f"name collision '{pref.id}'")
            self._by_id[pref.id] = pref

    def upd_from_form(self, form: ImmutableMultiDict[str, str]) -> None:
        for pref in self:
            pref.upd_from_form(form)

    def upd_from_cookies(self, cookies: dict[str, str]):
        for pref in self:
            pref.upd_from_cookies(cookies)

    def send_cookie(self, resp: flask.Response):
        for pref in self:
            pref.send_cookie(resp)
