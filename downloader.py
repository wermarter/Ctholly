import os
import requests
import threading
import time
import itertools

from multiprocessing.dummy import Pool as ThreadPool
from queue import Queue
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
    dl = FileDownloader(url)
    dl.run()


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
    Report (filename, downloaded, speed) to queue q.
    Raise DownloadFailed Exception"""

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
        return res, time.time()

    def run(self):
        res, t_start = self.try_to_get()
        if res is None:
            raise DownloadFailed("Max retries (3) exceeded.")
        with open(self.filename, 'wb') as out_file:
            downloaded = 0
            for chunk in res.iter_content(524288):
                if chunk:
                    t_end = time.time()
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    self.q.put((self.filename, downloaded, (downloaded/(t_end-t_start+1e-10))))
                    t_start = t_end
            res.close()


class FileDownloader(threading.Thread):
    """A class for multithreaded file downloading. 
    Can function normally with run() or start() as thread."""

    def __init__(self, url, file_dest='.', filename=None, n_thread=4, queue=None):
        super().__init__()
        # Preprocess input
        file_dest = os.path.normpath(file_dest)
        _filename, filesize, accept_range = get_file_info(url)
        if filename:
            file_dest = os.path.join(file_dest, filename)
            file_dest = filename_check(file_dest, True)
        else:
            file_dest = os.path.join(file_dest, _filename)
            file_dest = filename_check(file_dest, False)
        
        # Check for multithread support
        multithread = accept_range and filesize
        if (not multithread) and (n_thread > 1):
            n_thread=1

        self.queue = queue
        self._q = Queue()
        self.url = url
        self.file_dest = file_dest
        self.filesize = filesize
        self.n_thread = n_thread
        self.multithread = multithread

    def run(self):
        # Start download
        parts_info = []
        download_threads = []
        for i, (start, end) in enumerate(split_index(self.filesize, self.n_thread)):
            if not self.multithread:
                headers = None
            else:
                headers = {'Range': 'bytes=%d-%d' % (start, end-1)}
            filename_part = self.file_dest + '.part' + str(i)
            parts_info.append((filename_part, end-start))
            _thread = DownloadThread(self._q, self.url, filename_part, headers)
            _thread.start()
            download_threads.append(_thread)
            
        # Wait for download to finish
        for _thread in download_threads:
            _thread.join()

        # Join downloaded parts of file
        join_files(self.file_dest, sorted([i[0] for i in parts_info]), True)

class BatchDownloader(threading.Thread):
    """A class for downloading whole sh*t of files. 
    Can function normally with run() or start() as thread."""

    def __init__(self, urls, file_dest='.', filenames=None, n_thread=2, n_file=None, queue=None):
        super().__init__()
        if filenames is None:
            filenames = [None]*len(urls)
        if filenames == 'numeric':
            filenames = build_index_ext(urls)
        self.queue = queue
        self._q = Queue()
        self.n_thread = n_thread
        self.n_file = n_file
        self.urls = urls
        self.file_dest = file_dest
        self.file_dests = list()
        self.filenames = filenames
    
    def _download(self, args):
        url, filename = args
        # try:
        fd = FileDownloader(url, self.file_dest, filename, self.n_thread, self._q)
        self.file_dests.append(fd.file_dest)
        fd.run()
        # except Exception as e:
        #     print(e)
        #     self._q.put(('error', filename))

    def run(self):
        # Start download
        pool = ThreadPool(self.n_file)
        pool.map(self._download, zip(self.urls, self.filenames))

        pool.close()
        pool.join()
        if self.queue:
            pass
