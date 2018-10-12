#!/usr/bin/env python

try:
    unicode
except NameError:
    # Python 3
    unicode = str

from PySide2.QtWidgets import QMainWindow , QApplication, QAction, QListView, QTableView, QCheckBox, QLabel
from PySide2.QtGui import QTextCursor 
from PySide2.QtCore import QStringListModel
from PySide2 import QtWidgets as QtGui
from PySide2 import QtCore
from PySide2.QtCore import Qt
def fmt(x, *args):
    return x % args
import datetime
import functools
import io
import linecache
import os.path
import pickle
import sys
import tracemalloc
import xml.sax.saxutils

from tools import detect_encoding

SORT_ROLE = Qt.UserRole
MORE_TEXT = '...'

def escape_html(text):
    return xml.sax.saxutils.escape(text)

# FIXME
def tr(text):
    return text

class StatsModel(QtCore.QAbstractTableModel):
    def __init__(self, manager):
        QtCore.QAbstractTableModel.__init__(self, manager.window)
        self.manager = manager
        self.show_frames = 3
        self.tooltip_frames = 25
        self.set_stats(None, None, 'filename', False)

    def set_stats(self, snapshot1, snapshot2, group_by, cumulative):
        self.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))

        if snapshot1 is not None:
            if snapshot2 is not None:
                stats = snapshot2.compare_to(snapshot1, group_by, cumulative)
            else:
                stats = snapshot1.statistics(group_by, cumulative)
            self.stats = stats
            self.diff = isinstance(stats[0], tracemalloc.StatisticDiff)
            self.total = sum(stat.size for stat in self.stats)
            self.total_text = tracemalloc._format_size(self.total, False)
            if snapshot2 is not None:
                total1 = sum(trace.size for trace in snapshot1.traces)
                total2 = self.total
                self.total_text += ' (%s)' % tracemalloc._format_size(total2 - total1, True)
        else:
            self.stats = ()
            self.diff = False
            self.total = 0
            self.total_text = tracemalloc._format_size(0, False)

        self.group_by = group_by
        if self.group_by == 'traceback':
            source = self.tr("Traceback")
        elif self.group_by == 'lineno':
            source = self.tr("Line")
        else:
            source = self.tr("Filename")
        self.headers = [source, self.tr("Size")]
        if self.diff:
            self.headers.append(self.tr("Size Diff"))
        self.headers.append(self.tr("Count"))
        if self.diff:
            self.headers.append(self.tr("Count Diff"))
        self.headers.extend([self.tr("Item Size"), self.tr("%Total")])

        self.emit(QtCore.SIGNAL("layoutChanged()"))


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
        if role == Qt.ToolTipRole:
            if abs(size) < 10 * 1024:
                return None
            if diff:
                return "%+i" % size
            else:
                return str(size)
        return tracemalloc._format_size(size, diff)

    def format_frame(self, role, frame):
        filename = frame.filename

        if role == Qt.DisplayRole:
            filename = self.manager.format_filename(filename)
        elif role == Qt.ToolTipRole:
            filename = escape_html(filename)

        lineno = frame.lineno
        if self.group_by != "filename":
            if role == SORT_ROLE:
                return (filename, lineno)
            else:
                return "%s:%s" % (filename, lineno)
        else:
            return filename

    def _data(self, column, role, stat):
        if column == 0:
            if self.group_by == 'traceback':
                if role == Qt.ToolTipRole:
                    max_frames = self.tooltip_frames
                else:
                    max_frames = self.show_frames
                lines = []
                if role == Qt.ToolTipRole:
                    lines.append(self.tr("Traceback (most recent first):"))
                for frame in stat.traceback[:max_frames]:
                    line = self.format_frame(role, frame)
                    if role == Qt.ToolTipRole:
                        lines.append('&nbsp;' * 2 + line)
                        line = linecache.getline(frame.filename, frame.lineno).strip()
                        if line:
                            lines.append('&nbsp;' * 4 + '<b>%s</b>' % escape_html(line))
                    else:
                        lines.append(line)
                if len(stat.traceback) > max_frames:
                    lines.append(MORE_TEXT)
                if role == Qt.DisplayRole:
                    return ' <= '.join(lines)
                elif role == Qt.ToolTipRole:
                    return '<br />'.join(lines)
                else: # role == SORT_ROLE
                    return lines
            else:
                frame = stat.traceback[0]
                if role == Qt.ToolTipRole:
                    if frame.lineno:
                        line = linecache.getline(frame.filename, frame.lineno).strip()
                        if line:
                            return line
                        return None
                    else:
                        if role == Qt.ToolTipRole:
                            return frame.filename
                        return None
                else:
                    return self.format_frame(role, frame)

        if column == 1:
            size = stat.size
            return self.format_size(role, size, False)

        if self.diff:
            if column == 2:
                size = stat.size_diff
                return self.format_size(role, size, True)
            if column == 3:
                if role == Qt.ToolTipRole:
                    return None
                return stat.count
            if column == 4:
                if role == Qt.ToolTipRole:
                    return None
                return "%+d" % stat.count_diff
            if column == 5:
                # Item Size
                if stat.count:
                    size = stat.size / stat.count
                    return self.format_size(role, size, False)
                else:
                    return 0
        else:
            if column == 2:
                if role == Qt.ToolTipRole:
                    return None
                return stat.count
            if column == 3:
                # Item Size
                if not stat.count:
                    return 0
                size = stat.size / stat.count
                return self.format_size(role, size, False)

        # %Total
        if role == Qt.ToolTipRole:
            return None
        if not self.total:
            return 0
        percent = float(stat.size) / self.total
        if role == Qt.DisplayRole:
            return "%.1f %%" % (percent * 100.0)
        else:
            return percent

    def data(self, index, role):
        if not index.isValid():
            return None
        if role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        stat = self.stats[index.row()]
        column = index.column()
        return self._data(column, role, stat)

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[col]
        return None

    def sort(self, col, order):
        """sort table by given column number col"""
        self.emit(QtCore.SIGNAL("layoutAboutToBeChanged()"))
        self.stats = sorted(self.stats,
            key=functools.partial(self._data, col, SORT_ROLE),
            reverse=(order == Qt.DescendingOrder))
        self.emit(QtCore.SIGNAL("layoutChanged()"))


class HistoryState:
    def __init__(self, group_by, filters, cumulative):
        self.group_by = group_by
        self.filters = filters
        self.cumulative = cumulative


class History:
    def __init__(self, stats):
        self.stats = stats
        self.states = []
        self.index = -1

    def clear(self):
        del self.states[:]
        self.index = -1

    def append(self, state):
        if self.index != len(self.states) - 1:
            del self.states[self.index+1:]
        self.states.append(state)
        self.index += 1

    def restore_state(self):
        state = self.states[self.index]
        self.stats.restore_state(state)

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


class StatsManager:
    GROUP_BY = ['filename', 'lineno', 'traceback']
    # index in the combo box
    GROUP_BY_FILENAME = 0
    GROUP_BY_LINENO = 1
    GROUP_BY_TRACEBACK = 2

    def __init__(self, window, app):
        self.app = app
        self.window = window
        self.snapshots = window.snapshots
        self.source = window.source
        self.filename_parts = 3
        self._auto_refresh = False

        self.filters = []
        self.history = History(self)

        self.model = StatsModel(self)
        self.view = QTableView(window)
        self.view.setModel(self.model)
        self.cumulative_checkbox = QCheckBox(window.tr("Cumulative sizes"), window)
        self.group_by = QtGui.QComboBox(window)
        self.group_by.addItems([
            window.tr("Filename"),
            window.tr("Line number"),
            window.tr("Traceback"),
        ])

        self.filters_label = QLabel(window)
        self.summary = QLabel(window)
        self.view.verticalHeader().hide()
        self.view.resizeColumnsToContents()
        self.view.setSortingEnabled(True)

        window.connect(self.group_by, QtCore.SIGNAL("currentIndexChanged(int)"), self.group_by_changed)
        window.connect(self.view, QtCore.SIGNAL("doubleClicked(const QModelIndex&)"), self.double_clicked)
        window.connect(self.cumulative_checkbox, QtCore.SIGNAL("stateChanged(int)"), self.change_cumulative)
        window.connect(self.snapshots.load_button, QtCore.SIGNAL("clicked(bool)"), self.load_snapshots)
        window.connect(self.view.selectionModel(), QtCore.SIGNAL("selectionChanged(const QItemSelection&, const QItemSelection&)"), self.selection_changed)

        self.clear()
        self._auto_refresh = True

    def clear(self):
        del self.filters[:]
#        self.filters.append(tracemalloc.Filter(False, "<frozen importlib._bootstrap>"))
        self.cumulative_checkbox.setCheckState(Qt.Unchecked)
        self.group_by.setCurrentIndex(self.GROUP_BY_FILENAME)
        self.history.clear()
        self.append_history()
        self.refresh()

    def load_snapshots(self, checked):
        self.source.clear()
        self.clear()

    def append_history(self):
        group_by = self.group_by.currentIndex()
        filters = self.filters[:]
        cumulative = self.cumulative_checkbox.checkState()
        state = HistoryState(group_by, filters, cumulative)
        self.history.append(state)

    def restore_state(self, state):
        self.filters = state.filters[:]
        self._auto_refresh = False
        self.cumulative_checkbox.setCheckState(state.cumulative)
        self.group_by.setCurrentIndex(state.group_by)
        self._auto_refresh = True
        self.refresh()

    def format_filename(self, filename):
        parts = filename.split(os.path.sep)
        if len(parts) > self.filename_parts:
            parts = [MORE_TEXT] + parts[-self.filename_parts:]
        return os.path.join(*parts)

    def get_group_by(self):
        index = self.group_by.currentIndex()
        return self.GROUP_BY[index]

    def get_cumulative(self):
        return (self.cumulative_checkbox.checkState() == Qt.Checked)

    def refresh(self):
        group_by = self.get_group_by()
        if group_by != 'traceback':
            cumulative = self.get_cumulative()
        else:
            # FIXME: add visual feedback
            cumulative = False
        snapshot1, snapshot2 = self.snapshots.load_snapshots(self.filters)

        self.view.clearSelection()
        group_by = self.get_group_by()
        self.model.set_stats(snapshot1, snapshot2, group_by, cumulative)

        self.view.resizeColumnsToContents()
        self.view.sortByColumn(self.model.get_default_sort_column(), Qt.DescendingOrder)

        if self.filters:
            filters = []
            for filter in self.filters:
                text = self.format_filename(filter.filename_pattern)
                if filter.lineno:
                    text = "%s:%s" % (text, filter.lineno)
                if filter.all_frames:
                    text += self.window.tr(" (any frame)")
                if filter.inclusive:
                    text = fmt(self.window.tr("include %s"), text)
                else:
                    text = fmt(self.window.tr("exclude %s"), text)
                filters.append(text)
            filters_text = ", ".join(filters)
        else:
            filters_text = self.window.tr("(none)")
        filters_text = fmt(self.window.tr("Filters: %s"), filters_text)
        self.filters_label.setText(filters_text)

        total = self.model.total_text
        lines = len(self.model.stats)
        if group_by == 'filename':
            lines = fmt(self.window.tr("Files: %s"), lines)
        elif group_by == 'lineno':
            lines = fmt(self.window.tr("Lines: %s"), lines)
        else:
            lines = fmt(self.window.tr("Tracebacks: %s"), lines)
        total = fmt(self.window.tr("%s - Total: %s"), lines, total)
        self.summary.setText(total)

    def selection_changed(self, selected, unselected):
        indexes = selected.indexes()
        if not indexes:
            return
        stat = self.model.get_stat(indexes[0])
        if stat is None:
            return
        self.source.set_traceback(stat.traceback,
                                  self.get_group_by() != 'filename')
        self.source.show_frame(stat.traceback[0])

    def double_clicked(self, index):
        stat = self.model.get_stat(index)
        if stat is None:
            return
        group_by = self.get_group_by()
        if group_by == 'filename':
            all_frames = self.get_cumulative()
            self.filters.append(tracemalloc.Filter(True, stat.traceback[0].filename, all_frames=all_frames))
            self._auto_refresh = False
            self.group_by.setCurrentIndex(self.GROUP_BY_LINENO)
            self.append_history()
            self._auto_refresh = True
            self.refresh()
        elif group_by == 'lineno':
            # Replace filter by filename with filter by line
            new_filter = tracemalloc.Filter(True, stat.traceback[0].filename, stat.traceback[0].lineno, all_frames=False)
            if self.filters:
                old_filter = self.filters[-1]
                replace = (old_filter.inclusive == new_filter.inclusive
                           and old_filter.filename_pattern == new_filter.filename_pattern
                           and old_filter.lineno == None)
            else:
                replace = False
            if replace:
                self.filters[-1] = new_filter
            else:
                self.filters.append(new_filter)
            self._auto_refresh = False
            self.group_by.setCurrentIndex(self.GROUP_BY_TRACEBACK)
            self.append_history()
            self._auto_refresh = True
            self.refresh()

    def group_by_changed(self, index):
        if not self._auto_refresh:
            return
        self.append_history()
        self.refresh()

    def change_cumulative(self, state):
        if not self._auto_refresh:
            return
        self.append_history()
        self.refresh()


class MySnapshot:
    def __init__(self, filename):
        self.filename = filename
        ts = int(os.stat(filename).st_mtime)
        self.timestamp = datetime.datetime.fromtimestamp(ts)
        self.snapshot = None
        self.ntraces = None
        self.total = None

    def load(self):
        if self.snapshot is None:
            print("Load snapshot %s" % self.filename)
            with open(self.filename, "rb") as fp:
                self.snapshot = pickle.load(fp)
            self.ntraces = len(self.snapshot.traces)
            self.total = sum(trace.size for trace in self.snapshot.traces)
        return self.snapshot

    def unload(self):
        self.snapshot = None

    def get_label(self):
        if self.ntraces is None:
            print("Process snapshot %s..." % self.filename)
            # fill ntraces and total
            self.load()
            self.unload()
            print("Process snapshot %s... done" % self.filename)

        name = os.path.basename(self.filename)
        infos = [
            tracemalloc._format_size(self.total, False),
            fmt(tr("%s traces"), self.ntraces),
            str(self.timestamp),
        ]
        return "%s (%s)" % (name, ', '.join(infos))


class SnapshotManager:
    def __init__(self, parent):
        self.snapshots = []
        self.combo1 = QtGui.QComboBox(parent)
        self.combo1.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum))
        self.combo2 = QtGui.QComboBox(parent)
        self.combo2.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum))
        self.load_button = QtGui.QPushButton(tr("Load"), parent)
        self.load_button.setEnabled(True)

    def set_filenames(self, filenames):
        self.snapshots = [MySnapshot(filename) for filename in filenames]
        self.snapshots.sort(key=lambda snapshot: snapshot.timestamp)

        self.snapshots[0].load()
        if len(self.snapshots) > 1:
            self.snapshots[1].load()

        items = [snapshot.get_label() for snapshot in self.snapshots]
        self.combo1.addItems(items)
        self.combo1.setCurrentIndex(0)

        items = ['(none)'] + items
        self.combo2.addItems(items)
        if len(self.snapshots) > 1:
            self.combo2.setCurrentIndex(2)
        else:
            self.combo2.setCurrentIndex(0)

    def load_snapshots(self, filters):
        index1 = self.combo1.currentIndex()
        index2 = self.combo2.currentIndex()
        snapshot1 = self.snapshots[index1].load()
        snapshot2 = None
        if index2:
            index2 -= 1
            if index2 != index1:
                snapshot2 = self.snapshots[index2].load()
            else:
                self.combo2.setCurrentIndex(0)
        # FIXME: incremental filter
        if filters:
            snapshot1 = snapshot1.filter_traces(filters)
        if snapshot2 is not None:
            if filters:
                snapshot2 = snapshot2.filter_traces(filters)
        return (snapshot1, snapshot2)


class SourceCodeManager:
    def __init__(self, window):
        self.text_edit = QtGui.QTextEdit(window)
        self.text_edit.setReadOnly(True)
        # FIXME: write an optimized model
        self.traceback = None
        self.traceback_model = QStringListModel()
        self.traceback_view = QListView(window)
        self.traceback_view.setModel(self.traceback_model)
        self.traceback_view.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        window.connect(self.traceback_view.selectionModel(), QtCore.SIGNAL("selectionChanged(const QItemSelection&, const QItemSelection&)"), self.frame_selection_changed)
        # filename => (lines, mtime)
        self._file_cache = {}
        self.clear()

    def clear(self):
        self._current_file = None
        self._current_lineno = None
        self.traceback_model.setStringList([])
        self.text_edit.setText('')
        self._file_cache.clear()

    def frame_selection_changed(self, selected, unselected):
        indexes = selected.indexes()
        if not indexes:
            return
        row = indexes[0].row()
        frame = self.traceback[row]
        self.show_frame(frame)

    def set_traceback(self, traceback, show_lineno):
        self.traceback = traceback
        if show_lineno:
            lines = ['%s:%s' % (frame.filename, frame.lineno) for frame in traceback]
        else:
            lines = [frame.filename for frame in traceback]
        self.traceback_model.setStringList(lines)

    def read_file(self, filename):
        try:
            mtime = os.stat(filename).st_mtime
        except OSError:
            return None

        if filename in self._file_cache:
            text, cache_mtime = self._file_cache[filename]
            if mtime == cache_mtime:
                return text

        print("Read %s content (mtime: %s)" % (filename, mtime))
        with open(filename, 'rb') as fp:
            encoding, lines = detect_encoding(fp.readline)
        lineno = 1
        lines = []
        with io.open(filename, 'r', encoding=encoding) as fp:
            for lineno, line in enumerate(fp, 1):
                lines.append('%d: %s' % (lineno, line.rstrip()))

        text = '\n'.join(lines)
        self._file_cache[filename] = (text, mtime)
        return text

    def load_file(self, filename):
        if filename.startswith("<") and filename.startswith(">"):
            return False
        if self._current_file == filename:
            return True
        text = self.read_file(filename)
        if text is None:
            return False
        self.text_edit.setText(text)
        self._current_file = filename
        self._current_lineno = None
        return True

    def set_line_number(self, lineno):
        if self._current_lineno == lineno:
            return
        self._current_lineno = lineno
        doc = self.text_edit.document()
        # FIXME: complexity in O(number of lines)?
        block = doc.findBlockByLineNumber(lineno - 1)
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.BlockUnderCursor)
        # FIXME: complexity in O(number of lines)?
        self.text_edit.setTextCursor(cursor)

    def show_frame(self, frame):
        filename = frame.filename
        if not self.load_file(filename):
            self._current_file = None
            self.text_edit.setText('')
            return
        if frame.lineno > 0:
            self.set_line_number(frame.lineno)


class MainWindow(QMainWindow):
    def __init__(self, app, filenames):
        QMainWindow.__init__(self)
        self.setGeometry(300, 200, 1300, 450)
        self.setWindowTitle("Tracemalloc")

        # actions
        action_previous = QAction(self.tr("Previous"), self)
        self.connect(action_previous, QtCore.SIGNAL("triggered(bool)"), self.go_previous)
        action_next = QAction(self.tr("Next"), self)
        self.connect(action_next, QtCore.SIGNAL("triggered(bool)"), self.go_next)

        # toolbar
        toolbar = self.addToolBar(self.tr("Navigation"))
        toolbar.addAction(action_previous)
        toolbar.addAction(action_next)

        # create classes
        self.snapshots = SnapshotManager(self)
        self.snapshots.set_filenames(filenames)
        self.source = SourceCodeManager(self)
        self.stats = StatsManager(self, app)
        self.history = self.stats.history

        # snapshots
        hbox1 = QtGui.QHBoxLayout()
        hbox1.addWidget(QLabel(self.tr("Snapshot:")))
        hbox1.addWidget(self.snapshots.combo1)
        hbox2 = QtGui.QHBoxLayout()
        hbox2.addWidget(QLabel(self.tr("compared to:")))
        hbox2.addWidget(self.snapshots.combo2)

        vbox = QtGui.QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)

        hbox3 = QtGui.QHBoxLayout()
        hbox3.addLayout(vbox)
        hbox3.addWidget(self.snapshots.load_button)
        snap_box = QtGui.QWidget()
        snap_box.setLayout(hbox3)

        # Group by
        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(QLabel(self.tr("Group by:")))
        hbox.addWidget(self.stats.group_by)
        hbox.addWidget(self.stats.cumulative_checkbox)
        hbox.addWidget(self.stats.filters_label)
        self.stats.filters_label.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum))
        group_by_box = QtGui.QWidget()
        group_by_box.setLayout(hbox)

        # Source
        source_splitter = QtGui.QSplitter()
        source_splitter.addWidget(self.source.traceback_view)
        self.source.traceback_view.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Minimum))
        source_splitter.addWidget(self.source.text_edit)
        self.source.text_edit.setSizePolicy(QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding))

        # Top widgets
        layout = QtGui.QVBoxLayout()
        layout.addWidget(snap_box)
        layout.addWidget(group_by_box)
        layout.addWidget(self.stats.view)
        layout.addWidget(self.stats.summary)
        top_widget = QtGui.QWidget(self)
        top_widget.setLayout(layout)

        # main splitter
        main_splitter = QtGui.QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_widget)
        main_splitter.addWidget(source_splitter)
        self.setCentralWidget(main_splitter)

    def go_previous(self, checked):
        self.history.go_previous()

    def go_next(self, checked):
        self.history.go_next()


class Application:
    def __init__(self):
        if len(sys.argv) >= 2:
            filenames = sys.argv[1:]
        else:
            print("usage: %s snapshot1.pickle [snapshot2.pickle snapshot3.pickle ...]")
            sys.exit(1)

        # Create a Qt application
        self.app = QApplication(sys.argv)
        self.window = MainWindow(self, filenames)

    def main(self):
        self.window.show()
        self.app.exec_()
        sys.exit()


if __name__ == "__main__":
    Application().main()
