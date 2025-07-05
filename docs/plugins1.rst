============
Plugins ...
============

PDF
====

This plugin download :url: source as pdf.
This often fail in timeout so you can store your handmade pdf in pdf_store
(pdf_cache directory contains files automaticaly downloaded).
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


Usage
------------------

This plugin will save a pdf of the url (not link or local) for a source.

The pdf will be saved in osint_pdf_cache. If you can't create a pdf
for this url you will have an exception or an emply pdf.

In the case, you can print it manually and store it in osint_pdf_store
and remove the bad one in osint_pdf_cache. The name of the file is the source name + '.pdf'.

There is no authentication available for this process. So you must use the manual
printing for web sites that need one.


Known bugs
------------------

- when timeout occurs, the wkhtmltopdf isn't killed

Text
=====

.. code::

    pip install sphinxcontrib-osint[text]

This plugin download :url: source as text. Most of the 'parasite' text is
remove, trying to extract only human readable informations.
This rarely fail so you can store your handmade text file in text_store.
You can also change :url: to :link: to disable download.

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

Usage
------------------

This plugin will save a json of the url (not link or local) for a source.

It will downlaod the url and analyse it with trafilatura, and translate it
if configured for.

The json will be saved in osint_text_cache.

If you can't create a json for this url you will have an exception or an emply json.

In case you can't download text, you can add it manualy.
Create a text file with the name of the source, and add the text you copy/paste in it.
Then you can launch the command from the doc directory:

.. code::

    osint_text_import My_source_manualy_downloaded.txt

The json will be created, text will be translated (if needed) and saved
in text_store directory (files create automaticaly downloaded are in text_cache).
The corresponding analyste will be created on next doc build.


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


