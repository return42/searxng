# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

import types
import pathlib

from searx.answerers.random import answerer
import searx.utils

ANSWERERS_FOLDER = pathlib.Path(__file__).parent.absolute()
ANSWERERS_MAP: dict[str, tuple[types.ModuleType]] = {}


def load_answerers() -> dict[str, tuple[types.ModuleType]]:
    ret_val = {}

    for f_name in ANSWERERS_FOLDER.glob("*/answerer.py"):
        if not f_name.is_file or str(f_name.parent.name).startswith("_"):
            continue
        answ_name = f_name.parent.name
        module = searx.utils.load_module(answ_name, f_name)
        keywords = getattr(module, "keywords", ())
        if not keywords or not isinstance(keywords, tuple):
            raise ValueError(f"missing or invalid 'keyword' attribute in: {f_name}")
        ret_val[answ_name] = module

    return ret_val


def ask(query):
    results = []
    query_parts = list(filter(None, query.query.split()))

    if not query_parts or query_parts[0] not in ANSWERERS_MAP:
        return results

    for module in ANSWERERS_MAP.get(query_parts[0], ()):
        answer = module.answerer(query)
        if answer:
            results.append(answer)

    return results


ANSWERERS_MAP = load_answerers()
