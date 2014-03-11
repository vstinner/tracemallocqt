#!/usr/bin/env python

from PySide import QtCore
from PySide import QtGui
import datetime
import functools
import linecache
import operator
import os.path
import pickle
import sys
import tracemalloc

SORT_ROLE = QtCore.Qt.UserRole

class StatsModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, stats, group_by):
        QtCore.QAbstractTableModel.__init__(self, parent)

        self.stats = stats
        self.diff = isinstance(stats[0], tracemalloc.StatisticDiff)
        self.total = sum(stat.size for stat in stats)
        self.headers = [self.tr("Source"), self.tr("Size")]
        if self.diff:
            self.headers.append(self.tr("Size Diff"))
        self.headers.append(self.tr("Count"))
        if self.diff:
            self.headers.append(self.tr("Count Diff"))
        self.headers.extend([self.tr("Item Size"), self.tr("%Total")])
        self.filename_parts = 2
        self.show_lineno = (group_by != "filename")

    def get_default_sort_column(self):
        if self.diff:
            return 2
        else:
            return 1

    def rowCount(self, parent):
        return len(self.stats)

    def columnCount(self, parent):
        return len(self.headers)

    def get_stat(self, index):
        row = index.row()
        return self.stats[row]

    def format_size(self, role, size, diff):
        if role == SORT_ROLE:
            return size
        if role == QtCore.Qt.ToolTipRole:
            if size < 10 * 1024:
                return None
            if diff:
                return "%+i" % size
            else:
                return str(size)
        return tracemalloc._format_size(size, diff)

    def _data(self, column, role, stat):
        if column == 0:
            frame = stat.traceback[0]
            if role == QtCore.Qt.ToolTipRole:
                if frame.lineno:
                    line = linecache.getline(frame.filename, frame.lineno).strip()
                    if line:
                        return line
                return None
            else:
                filename = frame.filename
                parts = filename.split(os.path.sep)
                if role != SORT_ROLE and len(parts) > self.filename_parts:
                    parts = ['...'] + parts[-self.filename_parts:]
                filename = os.path.join(*parts)
                lineno = frame.lineno
                if self.show_lineno:
                    return "%s:%s" % (filename, lineno)
                else:
                    return filename

        if column == 1:
            size = stat.size
            return self.format_size(role, size, False)

        if self.diff:
            if column == 2:
                size = stat.size_diff
                return self.format_size(role, size, True)
            if column == 3:
                if role == QtCore.Qt.ToolTipRole:
                    return None
                return stat.count
            if column == 4:
                if role == QtCore.Qt.ToolTipRole:
                    return None
                return stat.count_diff
            if column == 5:
                # Item Size
                if stat.count:
                    size = stat.size / stat.count
                    return self.format_size(role, size, False)
                else:
                    return 0
        else:
            if column == 2:
                if role == QtCore.Qt.ToolTipRole:
                    return None
                return stat.count
            if column == 3:
                # Item Size
                if not stat.count:
                    return 0
                size = stat.size / stat.count
                return self.format_size(role, size, False)

        # %Total
        if role == QtCore.Qt.ToolTipRole:
            return None
        if not self.total:
            return 0
        percent = float(stat.size) / self.total
        if role == SORT_ROLE:
            return percent
        else:
            return "%.1f %%" % (percent * 100.0)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role not in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole):
            return None
        stat = self.stats[index.row()]
        column = index.column()
        return self._data(column, role, stat)

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.headers[col]
        return None

    def sort(self, col, order):
        """sort table by given column number col"""
        self.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))
        self.stats = sorted(self.stats,
            key=functools.partial(self._data, col, SORT_ROLE))
        # FIXME
        if order == QtCore.Qt.DescendingOrder:
            self.stats.reverse()
        self.emit(QtCore.SIGNAL("layoutChanged()"))


class HistoryState:
    def __init__(self, group_by, filters):
        self.group_by = group_by
        self.filters = filters[:]


class History:
    def __init__(self, stats):
        self.stats = stats
        self.states = []
        self.index = -1

    def append(self):
        state = HistoryState(self.stats.group_by, self.stats.filters)
        if self.index != len(self.states) - 1:
            del self.states[self.index+1:]
        self.states.append(state)
        self.index += 1

    def restore_state(self):
        state = self.states[self.index]
        self.stats.group_by = state.group_by
        self.stats.filters = state.filters[:]
        self.stats.refresh()

    def go_next(self):
        if self.index >= len(self.states) - 1:
            return
        self.index += 1
        self.restore_state()

    def go_previous(self):
        if self.index == 0:
            return
        self.index -= 1
        self.restore_state()


class Stats:
    def __init__(self, window, app):
        self.app = app
        self.window = window
        self.group_by = 'filename'
        self.filters = []
        self.history = History(self)
        self.history.append()

        self.view = QtGui.QTableView(window)
        self.summary = QtGui.QLabel(window)
        self.refresh()
        self.view.verticalHeader().hide()
        self.view.sortByColumn(self.model.get_default_sort_column(), QtCore.Qt.DescendingOrder)
        self.view.resizeColumnsToContents()
        self.view.setSortingEnabled(True)

    def refresh(self):
        snapshot1 = self.app.snapshot1.snapshot
        if self.filters:
            snapshot1 = snapshot1.filter_traces(self.filters)
        if self.app.snapshot2:
            snapshot2 = self.app.snapshot2.snapshot
            if self.filters:
                snapshot2 = snapshot2.filter_traces(self.filters)
            stats = snapshot2.compare_to(snapshot1, self.group_by)
        else:
            stats = snapshot1.statistics(self.group_by)
        self.model = StatsModel(self.window, stats, self.group_by)
        self.view.setModel(self.model)
        self.view.resizeColumnsToContents()

        total = tracemalloc._format_size(self.model.total, False)
        total = self.window.tr("Lines: %s - Total: %s") % (len(self.model.stats), total)
        self.summary.setText(total)

    def double_clicked(self, index):
        stat = self.model.get_stat(index)
        if stat is None:
            return
        if self.group_by == 'filename':
            self.filters.append(tracemalloc.Filter(True, stat.traceback[0].filename))
            self.group_by = 'lineno'
            self.history.append()
            self.refresh()


class MainWindow(QtGui.QMainWindow):
    def __init__(self, app):
        QtGui.QMainWindow.__init__(self)
        self.setGeometry(300, 200, 1300, 450)
        self.setWindowTitle("Tracemalloc")

        action_previous = QtGui.QAction(self.tr("Previous"), self)
        action_next = QtGui.QAction(self.tr("Next"), self)

        toolbar = self.addToolBar(self.tr("Navigation"))
        toolbar.addAction(action_previous)
        toolbar.addAction(action_next)

        self.stats = Stats(self, app)
        self.history = self.stats.history
        self.connect(self.stats.view, QtCore.SIGNAL("doubleClicked(const QModelIndex&)"), self.stats.double_clicked)
        self.connect(action_previous, QtCore.SIGNAL("triggered(bool)"), self.go_previous)
        self.connect(action_next, QtCore.SIGNAL("triggered(bool)"), self.go_next)

        widget = QtGui.QWidget(self)
        hbox = QtGui.QHBoxLayout(widget)
        file_info1 = QtGui.QLabel(app.snapshot1.get_label())
        hbox.addWidget(file_info1)
        if app.snapshot2:
            filename2 = os.path.basename(app.snapshot2.get_label())
        else:
            filename2 = '<none>'
        file_info2 = QtGui.QLabel(filename2)
        hbox.addWidget(file_info2)
        hboxw = QtGui.QWidget()
        hboxw.setLayout(hbox)

        layout = QtGui.QVBoxLayout(widget)
        layout.addWidget(hboxw)
        layout.addWidget(self.stats.view)
        layout.addWidget(self.stats.summary)
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def go_previous(self, checked):
        self.history.go_previous()

    def go_next(self, checked):
        self.history.go_next()

class MySnapshot:
    def __init__(self, filename):
        self.filename = filename
        ts = os.stat(filename).st_ctime
        self.timestamp = datetime.datetime.fromtimestamp(ts)
        with open(filename, "rb") as fp:
            self.snapshot = pickle.load(fp)

    def get_label(self):
        return "%s (%s)" % (os.path.basename(self.filename), self.timestamp)


class Application:
    def __init__(self):
        if len(sys.argv) == 2:
            filename1 = sys.argv[1]
            filename2 = None
        elif len(sys.argv) == 3:
            filename1 = sys.argv[1]
            filename2 = sys.argv[2]
        else:
            print("usage: %s snapshot1.pickle [snapshot2.pickle]")
            sys.exit(1)

        self.snapshot1 = MySnapshot(filename1)
        if filename2:
            self.snapshot2 = MySnapshot(filename2)
        else:
            self.snapshot2 = None

        # Create a Qt application
        self.app = QtGui.QApplication(sys.argv)
        self.window = MainWindow(self)

    def main(self):
        self.window.show()
        self.app.exec_()
        sys.exit()

if __name__ == "__main__":
    Application().main()
