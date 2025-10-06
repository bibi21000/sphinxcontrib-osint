Timeline
========

This plugin draw a timeline from events.

Installation
------------------

You need to install analyse dependencies

.. code::

    pip install sphinxcontrib-osint[timeline]

And enable it in your conf.py

.. code::

    osint_timeline_enabled = True

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.timeline import Timeline as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))


Indexes
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.timeline import Timeline as Plg
    for opt in Plg.Indexes():
        print('%s : %s' % (opt.name, opt.localname))


Directive Timeline
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.timeline import DirectiveTimeline as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


