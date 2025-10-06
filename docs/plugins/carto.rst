Carto
========

This plugin draw a world map with markers.

Installation
------------------

You need to install analyse dependencies

.. code::

    pip install sphinxcontrib-osint[carto]

And enable it in your conf.py

.. code::

    osint_carto_enabled = True

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.carto import Carto as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))


Indexes
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.carto import Carto as Plg
    for opt in Plg.Indexes():
        print('%s : %s' % (opt.name, opt.localname))


Directive Carto
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.carto import DirectiveCarto as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


