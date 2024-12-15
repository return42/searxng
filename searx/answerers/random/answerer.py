# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

from __future__ import annotations

import hashlib
import random
import string
import uuid
from flask_babel import gettext

from searx.result_types import Answer
from searx.result_types.answer import BaseAnswer

# required answerer attribute
# specifies which search query keywords triggers this answerer
keywords = ('random',)

random_int_max = 2**31
random_string_letters = string.ascii_lowercase + string.digits + string.ascii_uppercase


def random_characters():
    return [random.choice(random_string_letters) for _ in range(random.randint(8, 32))]


def random_string():
    return ''.join(random_characters())


def random_float():
    return str(random.random())


def random_int():
    return str(random.randint(-random_int_max, random_int_max))


def random_sha256():
    m = hashlib.sha256()
    m.update(''.join(random_characters()).encode())
    return str(m.hexdigest())


def random_uuid():
    return str(uuid.uuid4())


def random_color():
    color = "%06x" % random.randint(0, 0xFFFFFF)
    return f"#{color.upper()}"


random_types = {
    'string': random_string,
    'int': random_int,
    'float': random_float,
    'sha256': random_sha256,
    'uuid': random_uuid,
    'color': random_color,
}


def answer(query: str) -> list[BaseAnswer]:
    results = []
    parts = query.split()

    if len(parts) != 2 or parts[1] not in random_types:
        return results

    Answer(results=results, answer=random_types[parts[1]]())
    return results


def self_info():
    return {
        'name': gettext('Random value generator'),
        'description': gettext('Generate different random values'),
        'examples': ['random {}'.format(x) for x in random_types],
    }
