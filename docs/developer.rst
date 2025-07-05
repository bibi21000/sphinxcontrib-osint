Plugin's developer
====================

You can extend sphinxcontrib-osint using plugins.

Look at `official <https://github.com/bibi21000/sphinxcontrib-osint/tree/main/sphinxcontrib/osint/plugins>`_ plugins.
Plugin whois is the best and simple to check, text and pdf plugins are in an old format plugin(deprecated).

Add entrypoint:

.. code::

    [project.entry-points."sphinxcontrib.osint.plugin"]
    myplugin = "myplugin:MyPlugin"

Add code it:

.. code::

    from . import reify, PluginDirective

    class MyPlugin(PluginDirective):
        name = 'myplugin'
        order = 75

    ...

Your plugin will be disabled by default, enable it in your conf.py:

.. code::

    osint_myplugin_enabled = True

A config value osint_myplugin_enabled is created by default

Lazy imports:

When developing new plugins, you often need to load new modules.
This can be problematic is not all dependencies.
are installed. You can use lazy imports this problem.

First define a class property to import the wanted module in your plugin :

.. code::

    @classmethod
    @reify
    def _imp_json(cls):
        """Lazy loader for import json"""
        import importlib
        return importlib.import_module('json')

In other methods of youe plugin, you can now use :

.. code::

    def mymethod(self):

        data = self._imp_json.dumps({})
