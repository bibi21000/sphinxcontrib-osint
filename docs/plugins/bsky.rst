BlueSky
========

This plugin connect to bluesky.

Installation
------------------

You need to install whois dependencies

.. code::

    pip install sphinxcontrib-osint[bsky]

And enable it in your conf.py

.. code::

    osint_bsky_enabled = True

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.bsky import BSky as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))

Indexes
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.bsky import BSky as Plg
    for opt in Plg.Indexes():
        print('%s : %s' % (opt.name, opt.localname))

Directive bskypost
------------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.bsky import DirectiveBSkyPost as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))

Script
------------------

The following scripts are available :

.. program-output:: ../venv/bin/osint_bsky --help

