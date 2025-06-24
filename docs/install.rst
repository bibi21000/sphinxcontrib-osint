==========
Install
==========

Install

.. code::

    pip -U install sphinxcontrib-osint

If sphinx is not present, it will be automatically installed.


This package is not available in pypi right now, so you need to install
it using github.

Clone repository

.. code::

    git clone https://github.com/bibi21000/sphinxcontrib-osint.git

Change to directory

.. code::

    cd sphinxcontrib-osint

Make venv and install

.. code::

    python3 -m venv venv
    ./venv/bin/pip install .

Example

Build example demo

.. code::

    cd examples
    make html
