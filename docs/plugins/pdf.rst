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
