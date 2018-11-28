import os
import requests
import threading
import time
import itertools

from multiprocessing.dummy import Pool as ThreadPool
from queue import Queue
from tqdm import tqdm
from utils import (
    clear_lines,
    join_files,
    get_file_info,
    split_index,
    filename_check,
    sizeof_fmt,
    build_index_ext
)

def download_from_url(url):
    dl = FileDownloader(url, n_thread=8)
    dl.run()

def download_report(queue, total_size):
    downloaded = 0
    t = tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024)
    while downloaded < total_size:
        try:
            _part, _downloaded = queue.get(timeout=10)
        except:
            break
        downloaded += _downloaded
        t.update(_downloaded)
        queue.task_done()
    t.close()

#####################
# exception classes #
#####################


class DownloadFailed(Exception):
    def __init__(self, msg):
        super().__init__(msg)


######################
# downloader classes #
######################


class DownloadThread(threading.Thread):
    """A simple download worker working as thread.
    Report (filename, downloaded) to queue q.
    Raise DownloadFailed Exception."""

    def __init__(self, q, url, filename, headers=None):
        super().__init__()
        self.q = q
        self.url = url
        self.headers = headers
        self.filename = filename

    def try_to_get(self):
        tries, res = 0, None
        while (tries < 3):
            try:
                res = requests.get(self.url, stream=True, headers=self.headers, verify=False, allow_redirects=True)
                break
            except:
                tries += 1
        return res

    def run(self):
        res = self.try_to_get()
        if res is None:
            raise DownloadFailed("Max retries exceeded.")
        with open(self.filename, 'wb') as out_file:
            for chunk in res.iter_content(524288):
                if chunk:
                    out_file.write(chunk)
                    self.q.put((self.filename, len(chunk)))
            res.close()


class FileDownloader(threading.Thread):
    """A class for multithreaded file downloading. 
    Can function normally with run() or start() as thread."""

    def __init__(self, url, file_dest='.', filename=None, n_thread=4, report=True):
        super().__init__()

        # Preprocess file destination
        file_dest = os.path.normpath(file_dest)
        _filename, filesize, accept_range = get_file_info(url)
        if filename:
            file_dest = os.path.join(file_dest, filename)
        else:
            file_dest = os.path.join(file_dest, _filename)
        file_dest = filename_check(file_dest, True) 
        
        # Report can be handled externally by assigning a Queue to it
        self._q = Queue()
        self.queue = None
        if type(report) == Queue:
            self.queue = self._q
            self.report = False
        else:
            self.report = report

        # Check for multithread support
        multithread = accept_range and filesize
        if (not multithread) and (n_thread > 1):
            n_thread=1
            if self.report:
                print('[WARN] Multithread downloading not supported for this file.')

        self.url = url
        self.file_dest = file_dest
        self.filesize = filesize
        self.n_thread = n_thread
        self.multithread = multithread

    def run(self):
        # Start download threads
        download_threads = []
        part_names = []
        for i, (start, end) in enumerate(split_index(self.filesize, self.n_thread)):
            if not self.multithread:
                headers = None
            else:
                headers = {'Range': 'bytes=%d-%d' % (start, end-1)}
            part_name = self.file_dest + '.part' + str(i)
            part_names.append(part_name)
            _thread = DownloadThread(self._q, self.url, part_name, headers)
            _thread.start()
            download_threads.append(_thread)

        # Report progress
        if self.report:
            download_report(self._q, self.filesize)
        
        # Wait for download to finish
        for _thread in download_threads:
            _thread.join()

        # Join downloaded parts of file
        join_files(self.file_dest, sorted(part_names), self.report)

class BatchDownloader(threading.Thread):
    """A class for downloading whole sh*t of files. 
    Can function normally with run() or start() as thread."""

    def __init__(self, urls, file_dest='.', filenames=None, n_thread=2, n_file=4, report=True):
        super().__init__()

        # Filenames preprocessing
        if filenames is None:
            filenames = [None]*len(urls)
        if filenames == 'numeric':
            filenames = build_index_ext(urls)
        
        # Report can be handled externally by assigning a Queue to it
        self._q = Queue()
        self.queue = None
        if type(report) == Queue:
            self.queue = self._q
            self.report = False
        else:
            self.report = report

        self.n_thread = n_thread
        self.n_file = n_file
        self.urls = urls
        self.file_dest = file_dest
        self.file_dests = []
        self.errors = []
        self.filenames = filenames
        self.downloaders = []
        self.batch_size = 0

        # Initialize downloaders and calculate totle batch size
        self.size_queue = Queue()
        size_pool = ThreadPool(self.n_file)
        size_pool.map(self._fetch_meta, zip(self.urls, self.filenames))
        for _ in range(len(urls)):
            self.batch_size += self.size_queue.get()
        size_pool.close()
        size_pool.join()
    
    def _download(self, fd):
        try:
            fd.run()
        except Exception as e:
            print("@[{}]:\n{}".format(fd.filename, e))
            self.errors.append((fd.url, fd.filename))
    
    def _fetch_meta(self, url, filename):
        fd = FileDownloader(url, self.file_dest, filename, self.n_thread, self._q)
        self.file_dests.append(fd.file_dest)
        self.downloaders.append(fd)
        self.size_queue.put(fd.filesize)


    def run(self):
        # Start download
        pool = ThreadPool(self.n_file)
        pool.map(self._download, self.downloaders)

        # Report progress
        if self.report:
            download_report(self._q, self.batch_size)

        # Wait until downloaded
        pool.close()
        pool.join()
