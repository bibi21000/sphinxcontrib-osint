Youtube
========

This plugin download videos from youtbu.

Installation
------------------

You need to install youtube dependencies

.. code::

    pip install sphinxcontrib-osint[youtube]

And enable it in your conf.py

.. code::

    osint_youtube_enabled = True

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.youtube import Youtube as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))


Indexes
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.youtube import Youtube as Plg
    for opt in Plg.Indexes():
        print('%s : %s' % (opt.name, opt.localname))

Directive ytchannel
--------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.youtube import DirectiveYtChannel as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.youtube import DirectiveYtChannel as Directive
    print(Directive.__doc__)
