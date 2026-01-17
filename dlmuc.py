'''

'''
import os
import sys
from datetime import datetime
import importlib

# Completely disable fake_useragent by replacing it with a simple mock
class FakeUserAgentMock:
    """Mock class to replace fake_useragent"""
    random = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    
    def __init__(self, *args, **kwargs):
        pass
    
    @property
    def chrome(self):
        return self.random
    
    @property
    def firefox(self):
        return self.random
    
    @property
    def safari(self):
        return self.random

# Inject the mock before importing anything that uses fake_useragent
sys.modules['fake_useragent'] = type(sys)('fake_useragent')
sys.modules['fake_useragent'].UserAgent = FakeUserAgentMock
sys.modules['fake_useragent'].settings = type('obj', (object,), {'PATH': None, 'CACHE': None})()

import requests
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QCheckBox, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QProgressBar, QGridLayout, QMessageBox, QMenu, QAbstractItemView, QTextEdit, QStatusBar, QVBoxLayout, QHBoxLayout, QSplitter
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QCursor, QTextCursor
from musicdl import musicdl
from musicdl.modules.utils.misc import touchdir, sanitize_filepath


'''SearchThread - Search in background thread'''
class SearchThread(QThread):
    finished = pyqtSignal(dict)
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, music_client, keyword):
        super().__init__()
        self.music_client = music_client
        self.keyword = keyword
    
    def run(self):
        try:
            self.progress.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Starting search for: {self.keyword}")
            search_results = self.music_client.search(keyword=self.keyword)
            
            total_results = sum(len(results) for results in search_results.values())
            self.progress.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Search completed. Found {total_results} results.")
            
            self.finished.emit(search_results)
        except Exception as e:
            self.error.emit(f"Search failed: {str(e)}")


'''DownloadThread - Download in background thread'''
class DownloadThread(QThread):
    finished = pyqtSignal(str, str)
    progress = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    error = pyqtSignal(str)
    
    def __init__(self, music_client, song_info):
        super().__init__()
        self.music_client = music_client
        self.song_info = song_info
    
    def run(self):
        try:
            self.progress.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Starting download: {self.song_info['song_name']}")
            
            download_headers = self.music_client.music_clients[self.song_info['source']].default_download_headers
            
            with requests.get(self.song_info['download_url'], headers=download_headers, stream=True, timeout=30) as resp:
                if resp.status_code == 200:
                    total_size = int(resp.headers.get('content-length', 0))
                    chunk_size, download_size = 1024, 0
                    touchdir(self.song_info['work_dir'])
                    download_music_file_path = sanitize_filepath(os.path.join(self.song_info['work_dir'], self.song_info['song_name']+'.'+self.song_info['ext']))
                    
                    update_threshold = max(1, total_size // 100) if total_size > 0 else 1
                    last_update_size = 0
                    
                    with open(download_music_file_path, 'wb') as fp:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if not chunk: continue
                            fp.write(chunk)
                            download_size += len(chunk)
                            
                            if download_size - last_update_size >= update_threshold:
                                if total_size > 0:
                                    progress_percent = int(download_size / total_size * 100)
                                    self.update_progress.emit(progress_percent)
                                    self.progress.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Downloading... {progress_percent}% ({download_size}/{total_size} bytes)")
                                last_update_size = download_size
                    
                    self.update_progress.emit(100)
                    self.progress.emit(f"[{datetime.now().strftime('%H:%M:%S')}] Download completed: {download_music_file_path}")
                    self.finished.emit(self.song_info['song_name'], download_music_file_path)
                else:
                    self.error.emit(f"Server returned status code: {resp.status_code}")
        except requests.exceptions.RequestException as e:
            self.error.emit(f"Network error: {str(e)}")
        except Exception as e:
            self.error.emit(f"Download error: {str(e)}")


'''MusicdlGUI'''
class MusicdlGUI(QWidget):
    def __init__(self):
        super(MusicdlGUI, self).__init__()
        # initialize
        self.setWindowTitle('MusicdlGUI —— Charles的皮卡丘')
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), 'icon.ico')))
        self.setFixedSize(900, 700)
        self.initialize()
        
        # search sources
        self.src_names = ['QQMusicClient', 'KuwoMusicClient', 'MiguMusicClient', 'QianqianMusicClient', 'KugouMusicClient', 'NeteaseMusicClient']
        self.label_src = QLabel('Search Engine:')
        self.check_boxes = []
        for src in self.src_names:
            cb = QCheckBox(src, self)
            cb.setCheckState(QtCore.Qt.Checked)
            self.check_boxes.append(cb)
        
        # input boxes
        self.label_keyword = QLabel('Keywords:')
        self.lineedit_keyword = QLineEdit('尾戒')
        self.button_keyword = QPushButton('Search')
        
        # search results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(['ID', 'Singers', 'Songname', 'Filesize', 'Duration', 'Album', 'Source'])
        self.results_table.horizontalHeader().setStyleSheet("QHeaderView::section{background:skyblue;color:black;}")
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # mouse click menu
        self.context_menu = QMenu(self)
        self.action_download = self.context_menu.addAction('Download')
        
        # progress bar
        self.bar_download = QProgressBar(self)
        self.label_download = QLabel('Download progress:')
        
        # log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        self.log_output.setStyleSheet("background-color: #f0f0f0; font-family: Consolas, monospace; font-size: 9pt;")
        
        # status bar
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")
        
        # create splitter for table and log
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.addWidget(self.results_table)
        self.splitter.addWidget(self.log_output)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        
        # grid
        grid = QGridLayout()
        grid.addWidget(self.label_src, 0, 0, 1, 1)
        for idx, cb in enumerate(self.check_boxes): grid.addWidget(cb, 0, idx+1, 1, 1)
        grid.addWidget(self.label_keyword, 1, 0, 1, 1)
        grid.addWidget(self.lineedit_keyword, 1, 1, 1, len(self.src_names)-1)
        grid.addWidget(self.button_keyword, 1, len(self.src_names), 1, 1)
        grid.addWidget(self.label_download, 2, 0, 1, 1)
        grid.addWidget(self.bar_download, 2, 1, 1, len(self.src_names))
        grid.addWidget(self.splitter, 3, 0, 1, len(self.src_names)+1)
        grid.addWidget(self.status_bar, 4, 0, 1, len(self.src_names)+1)
        
        self.grid = grid
        self.setLayout(grid)
        
        # connect
        self.button_keyword.clicked.connect(self.search)
        self.results_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.results_table.customContextMenuRequested.connect(self.mouseclick)
        self.action_download.triggered.connect(self.download)
    
    def append_log(self, message):
        """Add message to log output"""
        self.log_output.append(message)
        # Auto scroll to bottom
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_output.setTextCursor(cursor)
    
    '''initialize'''
    def initialize(self):
        self.search_results = {}
        self.music_records = {}
        self.selected_music_idx = -10000
        self.music_client = None
        self.search_thread = None
        self.download_thread = None
    '''mouseclick'''
    def mouseclick(self):
        self.context_menu.move(QCursor().pos())
        self.context_menu.show()
    
    '''download'''
    def download(self):
        if not self.results_table.selectedItems():
            QMessageBox.warning(self, 'Warning', 'Please select a song to download')
            return
        
        self.selected_music_idx = str(self.results_table.selectedItems()[0].row())
        song_info = self.music_records.get(self.selected_music_idx)
        
        if not song_info:
            QMessageBox.warning(self, 'Error', 'Song information not found')
            return
        
        # Check if already downloading
        if self.download_thread and self.download_thread.isRunning():
            QMessageBox.warning(self, 'Warning', 'Another download is in progress')
            return
        
        # Start download in background thread
        self.download_thread = DownloadThread(self.music_client, song_info)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.progress.connect(self.append_log)
        self.download_thread.update_progress.connect(self.bar_download.setValue)
        self.download_thread.error.connect(self.on_download_error)
        self.download_thread.start()
        
        self.status_bar.showMessage(f"Downloading: {song_info['song_name']}")
        self.button_keyword.setEnabled(False)
    
    def on_download_finished(self, song_name, file_path):
        self.append_log(f"✓ Successfully downloaded: {song_name}")
        QMessageBox.information(self, 'Download Complete', f"Finished downloading {song_name}\nSaved to: {file_path}")
        self.status_bar.showMessage(f"Download complete: {song_name}")
        self.button_keyword.setEnabled(True)
    
    def on_download_error(self, error_msg):
        self.append_log(f"✗ Download error: {error_msg}")
        QMessageBox.critical(self, 'Download Error', error_msg)
        self.status_bar.showMessage(f"Download failed: {error_msg}")
        self.button_keyword.setEnabled(True)
        self.bar_download.setValue(0)
    
    '''search'''
    def search(self):
        # Check if already searching
        if self.search_thread and self.search_thread.isRunning():
            QMessageBox.warning(self, 'Warning', 'Search is in progress')
            return
        
        self.initialize()
        
        # selected music sources
        music_sources = []
        for cb in self.check_boxes:
            if cb.isChecked():
                music_sources.append(cb.text())
        
        if not music_sources:
            QMessageBox.warning(self, 'Warning', 'Please select at least one music source')
            return
        
        # keyword
        keyword = self.lineedit_keyword.text()
        if not keyword:
            QMessageBox.warning(self, 'Warning', 'Please enter a keyword')
            return
        
        # Clear log and results
        self.log_output.clear()
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Music sources: {', '.join(music_sources)}")
        self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Keyword: {keyword}")
        
        # Create music client
        try:
            self.music_client = musicdl.MusicClient(music_sources=music_sources)
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Music client initialized")
        except Exception as e:
            QMessageBox.critical(self, 'Error', f"Failed to initialize music client:\n{str(e)}")
            return
        
        # Start search in background thread
        self.search_thread = SearchThread(self.music_client, keyword)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.progress.connect(self.append_log)
        self.search_thread.error.connect(self.on_search_error)
        self.search_thread.start()
        
        self.status_bar.showMessage(f"Searching for: {keyword}")
        self.button_keyword.setEnabled(False)
        self.button_keyword.setText("Searching...")
    
    def on_search_finished(self, search_results):
        self.search_results = search_results
        
        # showing
        count, row = 0, 0
        for per_source_search_results in self.search_results.values():
            count += len(per_source_search_results)
        
        if count == 0:
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] No results found")
            QMessageBox.information(self, 'Search Result', 'No results found')
        else:
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Displaying {count} results")
            self.results_table.setRowCount(count)
            for _, (_, per_source_search_results) in enumerate(self.search_results.items()):
                for _, per_source_search_result in enumerate(per_source_search_results):
                    for column, item in enumerate([str(row), per_source_search_result['singers'], per_source_search_result['song_name'], per_source_search_result['file_size'], per_source_search_result['duration'], per_source_search_result['album'], per_source_search_result['source']]):
                        self.results_table.setItem(row, column, QTableWidgetItem(item))
                        self.results_table.item(row, column).setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                    self.music_records.update({str(row): per_source_search_result})
                    row += 1
        
        self.status_bar.showMessage(f"Search complete: {count} results found")
        self.button_keyword.setEnabled(True)
        self.button_keyword.setText("Search")
    
    def on_search_error(self, error_msg):
        self.append_log(f"✗ Search error: {error_msg}")
        QMessageBox.critical(self, 'Search Error', f"An error occurred during search:\n{error_msg}")
        self.status_bar.showMessage(f"Search failed: {error_msg}")
        self.button_keyword.setEnabled(True)
        self.button_keyword.setText("Search")


'''tests'''
if __name__ == '__main__':
    import traceback
    
    def exception_hook(exctype, value, tb):
        traceback.print_exception(exctype, value, tb)
        QMessageBox.critical(None, "Error", f"An unexpected error occurred:\n{str(value)}")
    
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    gui = MusicdlGUI()
    gui.show()

    sys.exit(app.exec_())
