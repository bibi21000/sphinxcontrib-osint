==========
Directives
==========

Configurations
================

The following configuration options are available :

.. exec_code::
    :hide:

    from sphinxcontrib.osint import config_values
    for opt in config_values:
        print('%s = %s' % (opt[0], opt[1]))

* osint_auths : a list of (domain, user, password, apikey)

Look at :ref:`cats <Cats>`.


.. _Indexes:

Indexes
================

The following indexes are available :

.. exec_code::
    :hide:

    from sphinxcontrib.osint import OSIntDomain

    for opt in OSIntDomain.indices:
        print('%s : %s' % (opt.name, opt.localname))


.. _Roles:

Roles
================

The following roles are available :

.. exec_code::
    :hide:

    from sphinxcontrib.osint import OSIntDomain

    for opt in OSIntDomain.roles:
        print('%s : %s' % (opt, OSIntDomain.roles[opt].__doc__))


.. _Scripts:

Script
================

The following scripts are available :

.. program-output:: osint_quest --help


.. _Directive Event:

Directive event
=====================

Represent an event : ie a meeting, an article, a manifestation, ...

You can create a :ref:`Link <Directive Link>` to an Event from an :ref:`Ident <Directive Ident>`.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveEvent as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveEvent as Directive
    print(Directive.__doc__)


.. _Directive Ident:

Directive ident
=====================

Represent an ident : ie a person, company, ...

You can create a :ref:`Relation <Directive Link>` from an Ident to an Ident.

You can create a :ref:`Link <Directive Link>` from an Ident to an :ref:`Event <Directive Event>`.

An ident can belong to one or many :ref:`orgs <Directive Org>`.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveIdent as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveIdent as Directive
    print(Directive.__doc__)


.. _Directive Link:

Directive link
=====================

Represent a link from an :ref:`Ident <Directive Ident>` to an :ref:`Event <Directive Event>`.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveLink as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveLink as Directive
    print(Directive.__doc__)


.. _Directive Org:

Directive org
=====================

Represent an organisation used in :ref:`idents <Directive Ident>`.

Use :ident: to automatically create an ident.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveOrg as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveOrg as Directive
    print(Directive.__doc__)


.. _Directive Country:

Directive country
=====================

Represent a country.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveCountry as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveCountry as Directive
    print(Directive.__doc__)


.. _Directive City:

Directive city
=====================

Represent a city.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveCity as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveCity as Directive
    print(Directive.__doc__)


.. _Directive Quote:

Directive quote
=====================

Represent a quote from an :ref:`Event <Directive Event>` to an :ref:`Event <Directive Event>`.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveQuote as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveQuote as Directive
    print(Directive.__doc__)


.. _Directive Relation:

Directive relation
=====================

Represent a relation from an :ref:`Ident <Directive Ident>` to an :ref:`Ident <Directive Ident>`.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveRelation as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveRelation as Directive
    print(Directive.__doc__)


.. _Directive Source:

Directive source
=====================

Represent a source. They are used for analyse, ...

A source can automatically created from an ident, event, ...
using the :source: and :link: (or other)


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveSource as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveSource as Directive
    print(Directive.__doc__)


url vs link vs local vs youtube vs bsky
-----------------------------------------------

* url : an http link that will be download for pdf and text processing.

* link : an http link that will be only be reported. No download at all.

* local : the full filename

* youtube : the url to a youtube video, the video will be downloaded (if enabled) and
  the subtitles will be downloaded and translates (if enabled)

* bksy : the url of a bsky post, the post and the following ones from
  the same user will be downloaded (if enabled)


.. _Directive Csv:

Directive csv
=====================

Filter data using orgs, cats and countries ang create csv to download.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveCsv as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveCsv as Directive
    print(Directive.__doc__)


.. _Directive Graph:

Directive graph
=====================

Filter data using orgs, cats and countries ang create a graph.

For colors, shapes, and styles, update different cats in conf.py by consulting the graphviz documentation :

    - `shapes <https://graphviz.org/doc/info/shapes.html#polygon>`_
    - `styles <https://graphviz.org/doc/info/shapes.html#styles-for-nodes>`_
    - `colors <https://graphviz.org/doc/info/colors.html>`_

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveGraph as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveGraph as Directive
    print(Directive.__doc__)


.. _Directive Report:

Directive report
=====================

Filter data using orgs, cats and countries ang create report in table.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveReport as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveReport as Directive
    print(Directive.__doc__)


.. _Directive SourceList:

Directive sourcelist
=====================

Filter data using orgs, cats and countries ang create list of sources in table.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveSourceList as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveSourceList as Directive
    print(Directive.__doc__)



.. _Directive EventList:

Directive eventlist
=====================

Filter data using orgs, cats and countries ang create list of events in table.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveEventList as Directive
    for opt in Directive.option_spec:
        print("%s : %s" % (opt, Directive.option_spec[opt].__name__))


.. exec_code::
    :hide:

    from sphinxcontrib.osint import DirectiveEventList as Directive
    print(Directive.__doc__)


.. _Cats:

Cats
==================

Categories are used to filter and represent data in graphs.

You can configure them with the following values in conf.py.
If a value is None, the osint_default_cats is used.

.. exec_code::
    :hide:

    from sphinxcontrib.osint import config_values
    for opt in config_values:
        if opt[0].endswith('_cats') is True:
            print('%s' % (opt[0]))

Here is a sample :

.. code::

    osint_default_cats = {
            'media' : {
                'shape' : 'egg',
                'style' : 'solid',
                'color' : 'blue',
            },
            'financial' : {
                'shape' : 'hexagon',
                'style' : 'solid',
            'fillcolor' : 'red',
            },
            'other' : {
                'shape' : 'octogon',
                'style' : 'dashed',
            },
        }

Graph are created using `graphviz <https://graphviz.org/doc/info/shapes.html#polygon>`_.

You can find more
`shapes <https://graphviz.org/doc/info/shapes.html#polygon>`_,
`styles <https://graphviz.org/doc/info/shapes.html#styles-for-nodes>`_
and `colors <https://graphviz.org/doc/info/colors.html>`_ in their documentation.
