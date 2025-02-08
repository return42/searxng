.. _settings plugins:

============
``plugins:``
============

.. sidebar:: Further reading ..

   - :ref:`plugins admin`
   - :ref:`dev plugin`

In SearXNG, plugins can be registered via a fully qualified class name and the
:py:obj:`PluginSettings <searx.plugins._core.PluginSettings>`.  The built-in
plugins are located in the namespace `searx.plugins`.

.. code:: yaml

   plugins:

     searx.plugins.self_info.SXNGPlugin:
       active: true

     searx.plugins.unit_converter.SXNGPlugin:
       active: false

In :ref:`plugins admin` you will find a list of the available plugins.
