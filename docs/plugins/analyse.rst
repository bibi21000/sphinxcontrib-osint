Analyse
========

This plugin analyse text retrieved from the text plugin.

The following engines are available :

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.analyselib import ENGINES
    for opt in ENGINES:
        print("%s" % (opt))

Installation
------------------

You need to install analyse dependencies

.. code::

    pip install sphinxcontrib-osint[analyse]

And enable it in your conf.py

.. code::

    osint_text_download = True
    osint_analyse_enabled = True

To define engines add in your conf.py

.. code::

    osint_analyse_engines = ['mood', 'words', 'people', 'countries']

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.analyse import Analyse as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))


Indexes
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.analyse import Analyse as Plg
    for opt in Plg.Indexes():
        print('%s : %s' % (opt.name, opt.localname))


Directive Analyse
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.analyselib import DirectiveAnalyse as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


Script
------------------

The following scripts are available :

.. program-output:: osint_analyse --help
