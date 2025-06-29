# sphinxcontrib-osint

Manage, archive and analyze your data collected during your OSInt quest and generate a report with sphinx.


## Install

Make venv and install

```
    python3 -m venv venv
    ./venv/bin/pip install sphinxcontrib-osint
```

## Example

Add data you grabbed to your rst file. For example, add an organization :

```
    .. osint:org:: github
        :label: Github
        :ident:
        :source:
        :url: https://github.com/
```

And another one :

```
    .. osint:org:: microsoft
        :label: Microsoft
        :ident:
```

And now a relation between them :

```
    .. osint:relation::
        :label: Buy
        :from: microsoft
        :to: github
        :begin: 2018-10-26
        :source:
        :url: https://en.wikipedia.org/wiki/GitHub#Acquisition_by_Microsoft
```

You can add organizations, identities, events and the relations between each others
and report then in graphs, tables or csv.

Look at [documentation](https://bibi21000.github.io/sphinxcontrib-osint/) for a step by step
tutorial or jump to the [demo](https://bibi21000.github.io/sphinxcontrib-osint/example/index.html).
