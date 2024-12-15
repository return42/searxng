# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

from __future__ import annotations
import hashlib
import re

from flask_babel import gettext

from searx.result_types import Answer

name = "Hash plugin"
description = gettext("Converts strings to different hash digests.")
default_on = True
preference_section = "query"
query_keywords = ['md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512']
query_examples = ['sha512 The quick brown fox jumps over the lazy dog']

parser_re = re.compile('(md5|sha1|sha224|sha256|sha384|sha512) (.*)', re.I)


def post_search(_request, search) -> list[Answer]:
    results = []

    # process only on first page
    if search.search_query.pageno > 1:
        return results
    m = parser_re.match(search.search_query.query)
    if not m:
        # wrong query
        return results

    function, string = m.groups()
    if not string.strip():
        # end if the string is empty
        return results

    # select hash function
    f = hashlib.new(function.lower())

    # make digest from the given string
    f.update(string.encode('utf-8').strip())
    answer = function + " " + gettext('hash digest') + ": " + f.hexdigest()

    Answer(results=results, answer=answer)

    return results
