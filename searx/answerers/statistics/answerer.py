# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring
from __future__ import annotations

from functools import reduce
from operator import mul

from flask_babel import gettext

from searx.result_types import Answer
from searx.result_types.answer import BaseAnswer

keywords = ('min', 'max', 'avg', 'sum', 'prod')


def answer(query: str) -> list[BaseAnswer]:
    results = []
    parts = query.split()

    if len(parts) < 2:
        return results

    try:
        args = list(map(float, parts[1:]))
    except:  # pylint: disable=bare-except
        # seems one of the args is not a float type, can't be converted to float
        return results

    func = parts[0]

    if func == 'min':
        Answer(results=results, answer=str(min(args)))
    elif func == 'max':
        Answer(results=results, answer=str(max(args)))
    elif func == 'avg':
        Answer(results=results, answer=str(sum(args) / len(args)))
    elif func == 'sum':
        Answer(results=results, answer=str(sum(args)))
    elif func == 'prod':
        Answer(results=results, answer=str(reduce(mul, args, 1)))

    return results


def self_info():
    return {
        'name': gettext('Statistics functions'),
        'description': gettext('Compute {functions} of the arguments').format(functions='/'.join(keywords)),
        'examples': ['avg 123 548 2.04 24.2'],
    }
