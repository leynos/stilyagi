"""Configure imports for duplication-gate script tests.

The gate's helper modules sit in ``scripts/`` beside this package, and the
tests import them by bare module name (``import duplication_gate``), so that
directory has to be importable. ``scripts/`` itself carries no
``__init__.py``: it is a directory of stand-alone scripts rather than a
package, and ``make duplication-test`` runs them with ``--rootdir=.`` and
``-c /dev/null``, so nothing else puts it on the path.

The entry is appended, not prepended. ``tests/`` is a real package here
(``tests/__init__.py`` exists), so unlike a PEP 420 namespace package it
cannot collide with this directory, and appending leaves the application's
own import resolution ahead of the gate's helper names. Prepending would let
a future ``scripts/tests/support.py`` shadow ``tests.support`` for the whole
run.
"""

import sys
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.append(str(SCRIPT_DIRECTORY))
