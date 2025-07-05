Whois
========

This plugin check whois of a domain.

Installation
------------------

You need to install whois dependencies

.. code::

    pip install sphinxcontrib-osint[whois]

And enable it in your conf.py

.. code::

    osint_whois_enabled = True

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.whois import Whois as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))


Indexes
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.whois import Whois as Plg
    for opt in Plg.Indexes():
        print('%s : %s' % (opt.name, opt.localname))

Directive whois
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.whois import DirectiveWhois as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


