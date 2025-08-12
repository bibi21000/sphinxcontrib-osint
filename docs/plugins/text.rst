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
if configured for. If a youtube video is given, the caption will be downloaded too.

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
