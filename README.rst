Qt GUI for tracemalloc.

* tracemallocqt: https://github.com/vstinner/tracemallocqt
* tracemalloc for Python 2.5-3.3: http://pytracemalloc.readthedocs.org/
* tracemalloc in Python 3.4: http://docs.python.org/dev/library/tracemalloc.html

Author: Victor Stinner <victor.stinner@gmail.com>


Usage
=====

Run your application, enable tracemalloc and dump snapshots with::

    import pickle, tracemalloc
    tracemalloc.start()
    # ... run your application ...
    snapshot = tracemalloc.take_snapshot()
    with open(filename, "wb") as fp:
        pickle.dump(snapshot, fp, 2)
    snapshot = None

Then open a snapshot with::

    python tracemallocqt.py snapshot.pickle

Compare two snapshots with::

    python tracemallocqt.py snapshot1.pickle snapshot2.pickle

You can specify any number of snapshots on the command line.


Dependencies
============

pytracemalloc works on Python 2 and Python 3. It supports PySide and PyQt4 (use
your preferred Qt binding). If PySide and PyQt4 are available, PySide is used.

* PyQt4: http://www.riverbankcomputing.co.uk/software/pyqt/intro
* PySide: http://qt-project.org/wiki/Get-PySide

  - Fedora: sudo yum install python-pyside
  - Debian: sudo apt-get install python-pyside.qtgui

