# SPDX-License-Identifier: AGPL-3.0-or-later
# lint: pylint
"""Suggestion item in the result list.  The suggestion result item is used in
the :origin:`infobox.html <searx/templates/simple/results.html>` template.

A sugestion item is a dictionary type with dedicated keys and values.

.. code:: python

   results.append({
       'suggestion' : str,
   })

The context ``suggestions`` of the HTML template is a set of dictionaries:

.. code:: python

   suggestions = [
       {
           'url'   : str,
           'title' : str,
       },
       {...},
       ...
   ]

url : ``str``
  The SearXNG search URL for the suggestion term.

title : ``str``
  The 'suggestion' string append by the engine.

"""

from typing import Set


def is_suggestion(result):
    """Returns ``True`` if result type is :py:obj:`.suggestion`, otherwise
    ``False``

    In the result list a suggestion item is identified by the existence of the
    key ``suggestion``.
    """
    return 'suggestion' in result


class Suggestions(Set):
    """Set of suggestions in the :py:obj:`.container.ResultContainer`"""
