#!/usr/bin/python

# Import PySide classes
import functools
import sys
import os.path
import operator
from PySide import QtCore
from PySide import QtGui

import pickle
import tracemalloc

class MyTableModel(QtCore.QAbstractTableModel):
    def __init__(self, parent, stats, group_by, *args):
        QtCore.QAbstractTableModel.__init__(self, parent, *args)
        self.stats = stats
        self.diff = isinstance(stats[0], tracemalloc.StatisticDiff)
        self.total = sum(stat.size for stat in stats)
        if self.diff:
            self.headers = ["Filename", "Size", "Size Diff", "Count", "Count Diff", "Item Size", "%Total"]
        else:
            self.headers = ["Filename", "Size", "Count", "Item Size", "%Total"]
        self.format_size = tracemalloc._format_size
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

    def _data(self, column, format, stat):
        if column == 0:
            frame = stat.traceback[0]
            filename = frame.filename
            parts = filename.split(os.path.sep)
            if len(parts) > self.filename_parts:
                parts = ['...'] + parts[-self.filename_parts:]
            filename = os.path.join(*parts)
            lineno = frame.lineno
            if self.show_lineno:
                return "%s:%s" % (filename, lineno)
            else:
                return filename
        if column == 1:
            size = stat.size
            if not format:
                return size
            return tracemalloc._format_size(size, False)
        if self.diff:
            if column == 2:
                size = stat.size_diff
                if not format:
                    return size
                return tracemalloc._format_size(size, True)
            if column == 3:
                return stat.count
            if column == 4:
                return stat.count_diff
            if column == 5:
                # Item Size
                if stat.count:
                    size = stat.size / stat.count
                    if not format:
                        return size
                    return tracemalloc._format_size(size, False)
                else:
                    return 0
        else:
            if column == 2:
                return stat.count
            if column == 3:
                # Item Size
                if not stat.count:
                    return 0
                size = stat.size / stat.count
                if not format:
                    return size
                return tracemalloc._format_size(size, False)
        if self.total:
            percent = float(stat.size) / self.total
            if not format:
                return percent
            return "%.1f %%" % (percent * 100.0)
        else:
            return 0

    def data(self, index, role):
        if not index.isValid():
            return None
        elif role != QtCore.Qt.DisplayRole:
            return None
        stat = self.stats[index.row()]
        column = index.column()
        return self._data(column, True, stat)

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.headers[col]
        return None

    def sort(self, col, order):
        """sort table by given column number col"""
        self.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))
        self.stats = sorted(self.stats,
            key=functools.partial(self._data, col, False))
        # FIXME
        if order == QtCore.Qt.DescendingOrder:
            self.stats.reverse()
        self.emit(QtCore.SIGNAL("layoutChanged()"))


class MyWindow(QtGui.QWidget):
    def __init__(self, app, *args):
        QtGui.QWidget.__init__(self, *args)
        # setGeometry(x_pos, y_pos, width, height)
        self.setGeometry(300, 200, 1300, 450)
        self.setWindowTitle("Tracemalloc")

        hbox = QtGui.QHBoxLayout()
        file_info1 = QtGui.QLabel(os.path.basename(app.filename1))
        hbox.addWidget(file_info1)
        file_info2 = QtGui.QLabel(os.path.basename(app.filename2))
        hbox.addWidget(file_info2)
        hboxw = QtGui.QWidget()
        hboxw.setLayout(hbox)

        if app.snapshot2:
            stats = app.snapshot2.compare_to(app.snapshot1, app.group_by)
        else:
            stats = app.snapshot1.statistics(app.group_by)

        self.stats_model = MyTableModel(self, stats, app.group_by)
        table_view = QtGui.QTableView()
        table_view.setModel(self.stats_model)
        # set column width to fit contents (set font first!)
        table_view.resizeColumnsToContents()
        # enable sorting
        table_view.verticalHeader().hide()
        table_view.sortByColumn(self.stats_model.get_default_sort_column(), QtCore.Qt.DescendingOrder)
        table_view.setSortingEnabled(True)

        total = tracemalloc._format_size(self.stats_model.total, False)
        summary = QtGui.QLabel("Lines: %s - Total: %s" % (len(stats), total))

        layout = QtGui.QVBoxLayout(self)
        layout.addWidget(hboxw)
        layout.addWidget(table_view)
        layout.addWidget(summary)
        self.setLayout(layout)


class MySnapshot:
    def __init__(self, filename):
        self.filename = filename
        with open(filename, "rb") as fp:
            self.snapshot = pickle.load(fp)

    def statistics(self, group_by):
        return self.snapshot.statistics(group_by)

    def compare_to(self, other, group_by):
        return self.snapshot.compare_to(other.snapshot, group_by)


class Application:
    def __init__(self):
        if len(sys.argv) == 2:
            self.filename1 = sys.argv[1]
            self.filename2 = None
        elif len(sys.argv) == 3:
            self.filename1 = sys.argv[1]
            self.filename2 = sys.argv[2]
        else:
            print("usage: %s snapshot1.pickle [snapshot2.pickle]")
            sys.exit(1)

        self.snapshot1 = MySnapshot(self.filename1)
        self.group_by = "lineno"
        if self.filename2:
            self.snapshot2 = MySnapshot(self.filename2)
        else:
            self.snapshot2 = None

        # Create a Qt application
        self.app = QtGui.QApplication(sys.argv)
        self.window = MyWindow(self)

    def main(self):
        self.window.show()
        self.app.exec_()
        sys.exit()

if __name__ == "__main__":
    Application().main()
