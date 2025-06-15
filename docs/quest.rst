==========
GitHub
==========

GitHub
==========

.. code::

    .. osint:org:: microsoft
        :label: Microsoft
        :ident:


.. code::

    .. osint:org:: github
        :label: Github
        :ident:
        :source:
        :url: https://github.com/

.. code::

    .. osint:event:: github_pages
        :label: GitHub Pages
        :source:
        :url: https://en.wikipedia.org/wiki/GitHub#GitHub_Pages
        :from: github
        :from-label: Launch
        :from-begin: 2001/01/01

.. code::

    .. osint:ident:: Thomas_Dohmke
        :cats: other
        :source:
        :label: Thomas Dohmke
        :link: https://www.linkedin.com/in/ashtom/
        :orgs: github

        He loves building products that make developers\' lives easier

.. code::

    .. osint:relation::
        :label: CEO
        :from: Thomas_Dohmke
        :to: github
        :begin: 2021/11/01


Microsoft
==========


.. code::

    .. osint:ident:: sun
        :label: Sun\nMicrosystems
        :from: Satya_Nadella
        :from-label: worked
        :from-end: 2014/01/01

.. code::

    .. osint:ident:: Satya_Nadella
        :label: Satya Nadella
        :source:
        :url: https://fr.wikipedia.org/wiki/Satya_Nadella
        :orgs: microsoft
        :cats: other
        :to: microsoft
        :to-label: CEO
        :to-begin: 2014/02/04

        Born 19 August 1967

.. code::

    .. osint:relation::
        :label: Buy
        :from: microsoft
        :to: github
        :begin: 2018/10/26

.. code::

    .. osint:source:: microsoft_github_buy
        :label: Acquisition
        :url: https://en.wikipedia.org/wiki/GitHub#Acquisition_by_Microsoft

.. code::

    .. osint:event:: azure_events
        :label: Azure\nevents
        :source:
        :link: https://azure.microsoft.com/en-us/resources/events
        :from: microsoft
        :from-label: Organize


All data
===========

.. code::

    .. osint:report:: full
       :label: full
       :caption: Full report

.. code::

    .. osint:graph:: full
       :label: full
       :caption: Full graph

.. code::

    .. osint:csv:: full
       :label: github
       :caption: Full csvs

.. code::

    Full csvs

        • Orgs
        • Idents
        • Events
        • Relations
        • Links

Github
===========

.. code::

    .. osint:graph:: github
       :label: github
       :caption: Github graph
       :orgs: github,microsoft



.. code::

    See :osint:ref:`Microosooft <ident.microsoft>`

    See :osint:ref:`ident.github`

==========
Indexes
==========

.. code::

    :ref:`osint-osint`

    :ref:`osint-sources`

    :ref:`osint-orgs`

    :ref:`osint-idents`

    :ref:`osint-relations`

    :ref:`osint-events`

    :ref:`osint-links`

    :ref:`osint-quotes`

    :ref:`osint-csvs`

    :ref:`osint-reports`

    :ref:`osint-graphs`
