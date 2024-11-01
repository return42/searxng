.. _settings engine:

===========
``engine:``
===========

.. sidebar:: Further reading ..

   - :ref:`configured engines`
   - :ref:`engines-dev`

A **engine instance** is configured by an engine item in the ``engines:`` list:

.. code:: yaml

   engines:
     - name: google
       shortcut: go
       engine: google

In the example from above a search engine named ``google`` with the shortcut
(aka !bang) ``!go`` is configured.  The python module with the engine
implementation is taken from python module :origin:`google.py
<searx/engines/google.py>`.

Several instances can be configured for an ``engine`` implementation, a typical
example being the :ref:`xpath engine` instances, or e.g. the the *codberg* and
*gitea.com* instances in the example below:

.. code:: yaml

  - name: codeberg
    engine: gitea
    base_url: https://codeberg.org
    shortcut: cb

  - name: gitea.com
    engine: gitea
    base_url: https://gitea.com
    shortcut: gitea

In the code example below a *full fledged* example of a YAML setup from a
dummy engine is shown.  Most of the options have a default value or even are
optional.

.. hint::

   A few more options are possible, but they are pretty specific to some
   engines (:ref:`engine implementations`).

.. code:: yaml

   - name: example engine
     engine: example
     shortcut: demo
     base_url: 'https://{language}.example.com/'
     send_accept_language_header: false
     categories: general
     timeout: 3.0
     api_key: 'apikey'
     disabled: false
     language: en_US
     tokens: [ 'my-secret-token' ]
     weight: 1
     display_error_messages: true
     about:
       website: https://example.com
       wikidata_id: Q306656
       official_api_documentation: https://example.com/api-doc
       use_official_api: true
       require_api_key: true
       results: HTML

     # overwrite values from section 'outgoing:'
     enable_http2: false
     retries: 1
     max_connections: 100
     max_keepalive_connections: 10
     keepalive_expiry: 5.0
     using_tor_proxy: false
     proxies:
       http:
         - http://proxy1:8080
         - http://proxy2:8080
       https:
         - http://proxy1:8080
         - http://proxy2:8080
         - socks5://user:password@proxy3:1080
         - socks5h://user:password@proxy4:1080

     # other network settings
     enable_http: false
     retry_on_http_error: true # or 403 or [404, 429]


Engine options
==============

.. autoclass:: searx.enginelib.engine::Engine
   :members: name, engine, shortcut, categories, timeout, disabled, inactive,
             weight, display_error_messages, paging, max_page,
             time_range_support, safesearch, language_support, language, region,
             about, api_key, base_url, tokens, enable_http, network, proxies,
             send_accept_language_header, retry_on_http_error, network, proxies,
             using_tor_proxy, max_keepalive_connections, max_connections,
             keepalive_expiry


.. _private engines:

Private Engines (``tokens``)
============================

Administrators might find themselves wanting to limit access to some of the
enabled engines on their instances.  It might be because they do not want to
expose some private information through :ref:`offline engines`.  Or they would
rather share engines only with their trusted friends or colleagues.

.. sidebar:: info

   Initial sponsored by `Search and Discovery Fund
   <https://nlnet.nl/discovery>`_ of `NLnet Foundation <https://nlnet.nl/>`_.

To solve this issue the concept of *private engines* exists.

A new option was added to engines named `tokens`.  It expects a list of strings.
If the user making a request presents one of the tokens of an engine, they can
access information about the engine and make search requests.

Example configuration to restrict access to the Arch Linux Wiki engine:

.. code:: yaml

  - name: arch linux wiki
    engine: archlinux
    shortcut: al
    tokens: [ 'my-secret-token' ]

Unless a user has configured the right token, the engine is going to be hidden
from them.  It is not going to be included in the list of engines on the
Preferences page and in the output of `/config` REST API call.

Tokens can be added to one's configuration on the Preferences page under "Engine
tokens".  The input expects a comma separated list of strings.

The distribution of the tokens from the administrator to the users is not carved
in stone.  As providing access to such engines implies that the admin knows and
trusts the user, we do not see necessary to come up with a strict process.
Instead, we would like to add guidelines to the documentation of the feature.


Example: Multilingual Search
============================

SearXNG does not support true multilingual search.  You have to use the language
prefix in your search query when searching in a different language.

But there is a workaround: By adding a new search engine with a different
language, SearXNG will search in your default and other language.

Example configuration in settings.yml for a German and English speaker:

.. code-block:: yaml

    search:
        default_lang : "de"
        ...

    engines:
      - name : google english
        engine : google
        language : en
        ...

When searching, the default google engine will return German results and
"google english" will return English results.
