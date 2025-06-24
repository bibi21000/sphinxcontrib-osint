==========
Install
==========

Install

.. code::

    pip -U install sphinxcontrib-osint

If sphinx is not present, it will be automatically installed.

Create a directory for your quest and cd to it:

.. code::

    mkdir myquest
    cd myquest

Create your quest structure using sphinx-quickstart:

.. code::

    sphinx-quickstart

.. code::

    Welcome to the Sphinx 8.1.3 quickstart utility.

    Please enter values for the following settings (just press Enter to
    accept a default value, if one is given in brackets).

    Selected root path: .

.. code::

    You have two options for placing the build directory for Sphinx output.
    Either, you use a directory "_build" within the root path, or you separate
    "source" and "build" directories within the root path.
    > Separate source and build directories (y/n) [n]: n

.. code::

    The project name will occur in several places in the built documentation.

.. code::

    > Project name: MyQuest
    > Author name(s): AnonyMouse
    > Project release []: 0.0.1

.. code::

    If the documents are to be written in a language other than English,
    you can select a language here by its language code. Sphinx will then
    translate text that it generates into that language.

    For a list of supported codes, see
    https://www.sphinx-doc.org/en/master/usage/configuration.html#confval-language.
    > Project language [en]: en

.. code::

    Creating file /*****/test/conf.py.
    Creating file /*****/test/index.rst.
    Creating file /*****/test/Makefile.
    Creating file /*****/test/make.bat.

    Finished: An initial directory structure has been created.

    You should now populate your master file /home/sebastien/devel/OSInt/sphinxcontrib-osint/test/index.rst and create other documentation
    source files. Use the Makefile to build the docs, like so:
       make builder
    where "builder" is one of the supported builders, e.g. html, latex or linkcheck.

You can check files and directories created :

.. code::

    ls

.. code::

    _build  conf.py  index.rst  make.bat  Makefile  _static  _templates

