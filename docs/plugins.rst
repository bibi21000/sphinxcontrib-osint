==========
Plugins
==========

PDF
====

This plugin download :url: source as pdf.
This often fail in timeout so you can store your handmade pdf in pdf_store.
You can also change :url: to :link: to disable download.

Installation
------------------

You need to install pdf dependencies

.. code::

    pip install sphinxcontrib-osint[pdf]


And install wkhtmltopdf tools:

    Debian/Ubuntu:

    .. code::

        sudo apt-get install wkhtmltopdf

    macOS:

    .. code::

        brew install homebrew/cask/wkhtmltopdf

    Windows and other options: check `wkhtmltopdf homepage <https://wkhtmltopdf.org/>`_ for binary installers


And enable it in your conf.py

.. code::

    osint_pdf_download = True

Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.pdf import Pdf as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))


Text
=====

.. code::

    pip install sphinxcontrib-osint[text]

This plugin download :url: source as text. Most of the 'parasite' text is
remove, trying to extract only human readable informations.
This rarely fail so you can store your handmade text file in text_store.
You can also change :url: to :link: to disable download.

You can save the original file just after download (.orig.txt) and
you can activate automatique translation.

Installation
------------------

You need to install text dependencies

.. code::

    pip install sphinxcontrib-osint[text]


And enable it in your conf.py

.. code::

    osint_text_download = True

To enable translation add in your conf.py

.. code::

    osint_text_translate = 'en'


Configurations
------------------

.. exec_code::
    :hide:

    from sphinxcontrib.osint.plugins.text import Text as Plg
    for opt in Plg.config_values():
        print('%s = %s' % (opt[0], opt[1]))

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

