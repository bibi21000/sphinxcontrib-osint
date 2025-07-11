﻿==========
Quest
==========

Open quest.rst

You found an interesting organisation and want to add it to your quest.
Add the following lines:

.. code::

    .. osint:org:: github
        :label: Github
        :ident:
        :source:
        :url: https://github.com/

With this few lines you added :

    - an :ref:`Org <Directive Org>`
    - an :ref:`Ident <Directive Ident>`
    - a :ref:`Source <Directive Source>`

.. note::

    After a directive you can declare an argument :

    .. code::

        . osint:org:: argument

    This argument will be a key in the osint, so need to be unique.
    It can be the file name of the data saved locally and will be
    used in graph definitions too.

    So don't use any of the punctuation characters, accuented characters, space, comma, ...
    Better to use only alphanumeric characters and _


In your deep quest, you found another small company :

.. code::

    .. osint:org:: microsoft
        :label: Microsoft
        :ident:

Wow ... what an interesting event ... Github launched github pages !!!

.. code::

    .. osint:event:: github_pages
        :label: GitHub Pages
        :source:
        :url: https://en.wikipedia.org/wiki/GitHub#GitHub_Pages
        :from: github
        :from-label: Launch
        :begin: 2001-01-01

With this few lines you added :

    - an :ref:`Event <Directive Event>`
    - a :ref:`Link <Directive Link>` from Ident **github** to event **github_pages**

A new ident to add ... this guy work for Microsoft !!!
And we have his birth date too.

.. code::

    .. osint:ident:: Satya_Nadella
        :label: Satya Nadella
        :source:
        :url: https://fr.wikipedia.org/wiki/Satya_Nadella
        :orgs: microsoft
        :cats: other
        :to: microsoft
        :to-label: CEO
        :to-begin: 2014-02-04

        Born 19 August 1967

With this few lines you added :

    - an :ref:`Ident <Directive Ident>`
    - a :ref:`Source <Directive Source>`
    - a :ref:`Relation <Directive Event>` from **Satya_Nadella** to **microsoft**
    - some free text

...

Now it's time to add `reports <report.html>`_ in your quest.
