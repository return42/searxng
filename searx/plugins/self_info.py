# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring

from __future__ import annotations

import re
from flask_babel import gettext

from searx.botdetection._helpers import get_real_ip
from searx.result_types import Answer


name = gettext('Self Information')
description = gettext('Displays your IP if the query is "ip" and your user agent if the query is "user-agent".')
default_on = True
preference_section = 'query'
query_keywords = ["ip", "user-agent"]

# "ip" or "my ip" regex
ip_regex = re.compile('^ip$', re.IGNORECASE)

# Self User Agent regex
ua_regex = re.compile('^user-agent$', re.IGNORECASE)


def post_search(request, search) -> list[Answer]:
    results = []

    if search.search_query.pageno > 1:
        return results

    if ip_regex.search(search.search_query.query):
        Answer(results=results, answer=gettext('Your IP is: ') + get_real_ip(request))

    if ua_regex.match(search.search_query.query):
        Answer(results=results, answer=gettext('Your user-agent is: ') + request.user_agent.string)

    return results
