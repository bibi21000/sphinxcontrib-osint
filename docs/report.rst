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

You can also add a link to one entry using

.. code::

    :osint:ref:`ident.github`

All is here, time to generate the quest and open _build/html/index.html in your favorite browser.

.. code::

    make doc

If you have problem to generate the quest, clean it before :

.. code::

    make clean
    make doc

You can change the template used for the html ages in conf.py.

.. code::

    html_theme = 'alabaster'

Try to change it to 'traditional', 'scrolls', 'nature', ... Look at these `templates <https://sphinx-themes.org/>`_

Documentation will be built in _build/html. The best way to access it locally is to launch
an http server. Python can do it for you simply.

.. code::

    cd _build/html/ && python3 -m http.server 8888

And now open http://127.0.0.1:8888 in your favorite web browser.

What to do next ? Look at the `directives <directives.html>`_ details
and `plugins <plugins.html>`_ fucntionalities.

For the **developpers**, sphinxcontrib-osint support plugins. Look at `developer <developer.html>`_ page.

Look at the `source <https://github.com/bibi21000/sphinxcontrib-osint/tree/main/example>`_ of the
example quest and visit the `quest <example/index.html>`_ generated.
