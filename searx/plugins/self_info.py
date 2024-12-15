# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,invalid-name

import re
from flask_babel import gettext

from searx.botdetection._helpers import get_real_ip
from searx.result_types import Answer

name = gettext('Self Information')
description = gettext('Displays your IP if the query is "ip" and your user agent if the query contains "user agent".')
default_on = True
preference_section = 'query'
query_keywords = ['user-agent']
query_examples = ''

# "ip" or "my ip" regex
ip_regex = re.compile('^ip$|my ip', re.IGNORECASE)

# Self User Agent regex
ua_regex = re.compile('.*user[ -]agent.*', re.IGNORECASE)


def post_search(request, search):

    results = []

    if search.search_query.pageno > 1:
        return True

    if ip_regex.search(search.search_query.query):
        ip = get_real_ip(request)
        Answer(results=results, answer=gettext('Your IP is: ') + ip)

    if ua_regex.match(search.search_query.query):
        ua = request.user_agent
        Answer(results=results, answer=gettext('Your user-agent is: ') + ua.string)

    return results
