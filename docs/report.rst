==========
Reporting
==========

After adding data, you will need to report and analyse them.
Data can filtered using orgs, cats and countries.

The first way to visualize data is a :ref:`Graph <Directive Graph>`. It will show you relations and
links between events and idents.

.. code::

    .. osint:graph:: full
       :label: full
       :caption: Full graph

Another way is the table :ref:`Report <Directive Report>` :

.. code::

    .. osint:report:: full
       :label: full
       :caption: Full report

If you want to export your data, you can check the :ref:`Csv <Directive Csv>` directive.

Data are indexed in multiples :ref:`indexes <Indexes>`. You can add a link
to them using :

.. code::

    :ref:`osint-osint`

You can also add a link to the entry using

.. code::

    :osint:ref:`ident.github`

All is here, time to generate the quest and open _build/html/index.html in your favorite browser.

.. code::

    make doc

If you have problem to generate the quest, clean it before :

.. code::

    make clean
    make doc

What to do next ? Look at the `directives <directives.html>`_ details
and `plugins <plugins.html>`_ fucntionalities.

Visit the `example <example/index.html>`_ quest.
