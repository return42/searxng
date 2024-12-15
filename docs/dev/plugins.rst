.. _dev plugin:

=======
Plugins
=======

.. automodule:: searx.plugins
   :members:




External plugins
================

SearXNG supports *external plugins* / there is no need to install one, SearXNG
runs out of the box.  But to demonstrate; in the example below we install the
SearXNG plugins from *The Green Web Foundation* `[ref]
<https://www.thegreenwebfoundation.org/news/searching-the-green-web-with-searx/>`__:

.. code:: bash

   $ sudo utils/searxng.sh instance cmd bash -c
   (searxng-pyenv)$ pip install git+https://github.com/return42/tgwf-searx-plugins

In the :ref:`settings.yml` activate the ``plugins:`` section and add module
``only_show_green_results`` from ``tgwf-searx-plugins``.

.. code:: yaml

   plugins:
     ...
     - only_show_green_results
     ...


