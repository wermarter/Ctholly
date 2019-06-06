import os
import threading
from multiprocessing.dummy import Pool as ThreadPool
from queue import Queue

from tqdm import tqdm

from ctholly.utils import (build_index_filename,
                           fix_filename,
                           get_file_info,
                           join_files,
                           split_index,
                           get_size_downloaded,
                           retry_session)


def download_file(url):
    downloader = FileDownloader(url, n_thread=2)
    downloader.run()


def report_download_queue(queue, total_size):
    downloaded = 0
    t = tqdm(total=total_size,
             unit='B',
             unit_scale=True,
             unit_divisor=1024)
    while downloaded < total_size:
        msg = queue.get()
        if msg == "DONE":
            break
        _part, _downloaded = msg
        downloaded += _downloaded
        t.update(_downloaded)
        queue.task_done()
    t.close()


class DownloadThread(threading.Thread):
    def __init__(self, report_queue, url, filename, headers=None):
        super().__init__()
        self.report_queue = report_queue
        self.url = url
        self.filename = filename
        self.headers = dict(headers)

    def try_to_get(self):
        session = retry_session()
        response = session.get(self.url, stream=True, headers=self.headers,
                               verify=False, allow_redirects=True)
        return response

    def run(self):
        response = self.try_to_get()
        with open(self.filename, 'ab') as out_file:
            for chunk in response.iter_content(1024 * 1024):
                out_file.write(chunk)
                self.report_queue.put((self.filename, len(chunk)))


class FileDownloader(threading.Thread):
    """A class for multithreaded file downloading. 
    Can function normally with run() or start() as thread.
    * Auto resumption if file existed."""

    def __init__(self, url,
                 directory='.',
                 filename=None,
                 n_thread=8,
                 report=True,
                 overwrite=False,
                 headers=None):
        super().__init__()

        # Report can be handled externally by assigning a Queue to it
        if type(report) == Queue:
            self._q = report
            self.report = False
        else:
            self.report = report
            self._q = Queue()

        self.headers = headers or {}

        # Check for multithread support
        try:
            _filename, filesize, accept_range = get_file_info(
                url, input_header=self.headers
            )
        except:
            self._non_downloadable = True
            if self.report:
                print('[WARN] Non-downloadable content:', url)
            return
        else:
            self._non_downloadable = False
        
        multithread = accept_range and filesize
        if (not multithread) and (n_thread > 1):
            n_thread = 1
            if self.report:
                print('[WARN] Multithread downloading not supported for this file.')

        # Preprocess file destination
        directory = os.path.normpath(directory)
        filename = fix_filename(filename or _filename)
        filename = os.path.join(directory, filename)
        start_pos = get_size_downloaded(filename)

        # Download resumption
        if not overwrite:
            if len(start_pos) == 0:
                self.start_pos = [0] * n_thread
            elif (start_pos[0] != 0) and (len(start_pos) > 1):
                if self.report:
                    print('Found', len(start_pos),
                          'downloaded parts. Resuming...')
                self.start_pos = start_pos
                n_thread = len(start_pos)

        self.filename = filename
        self.url = url
        self.filesize = filesize
        self.n_thread = n_thread
        self.multithread = multithread

    def run(self):

        # Sanity check
        if self._non_downloadable:
            return

        # Start download threads
        download_threads = []
        part_names = []
        part_sizes = []

        for i, (start, end) in enumerate(split_index(self.filesize, self.n_thread)):
            if self.multithread:
                self.headers.update(
                    {'Range': 'bytes=%d-%d' % (self.start_pos[i] + start, end - 1)})
            part_name = self.filename + '.part' + str(i)
            part_names.append(part_name)
            part_sizes.append(end - start + 1)
            _thread = DownloadThread(
                self._q, self.url, part_name, self.headers)
            _thread.start()
            download_threads.append(_thread)

        # Report progress
        if self.report:
            report_thread = threading.Thread(target=report_download_queue,
                                             args=(self._q, self.filesize - sum(self.start_pos)))
            report_thread.start()

        # Wait for download to finish
        for _thread in download_threads:
            _thread.join()

        # Close reporter
        if self.report:
            self._q.put('DONE')
            report_thread.join()

        # Check part size
        for (fname, fsize) in zip(part_names, part_sizes):
            actual_size = os.path.getsize(fname)
            if fsize != fsize:
                print(f"{actual_size} <> {fsize}")
                return

        # Join downloaded parts of file
        join_files(self.filename, part_names, self.report)

        # Filesize check
        actual_size = os.path.getsize(self.filename)
        if actual_size != self.filesize:
            if self.report:
                delete = input(
                    "Size mismatched [%s/%s]. Delete? " % (actual_size, self.filesize))
                delete = True if str(delete).upper()[0] == 'Y' else False
                if delete:
                    os.remove(self.filename)
            else:
                raise Exception(
                    "Size mismatched [%s/%s]." % (actual_size, self.filesize))


class BatchDownloader(threading.Thread):
    """A class for downloading whole sh*t of files. 
    Can function normally with run() or start() as thread."""

    def __init__(self, urls, file_dest='.', filenames=None, n_thread=4, n_file=4, report=True, headers={}):
        super().__init__()

        # Filenames preprocessing
        if filenames is None:
            filenames = [None] * len(urls)
        if filenames == 'numeric':
            filenames = build_index_filename(urls)

        # Report can be handled externally by assigning a Queue to it
        if type(report) == Queue:
            self._q = report
            self.report = False
        else:
            self.report = report
            self._q = Queue()

        self.n_thread = n_thread
        self.n_file = n_file
        self.urls = urls
        self.file_dest = file_dest
        self.file_dests = []
        self.errors = []
        self.filenames = filenames
        self.downloaders = []
        self.batch_size = 0
        self.headers = headers

        # Initialize downloaders and calculate total batch size
        with ThreadPool(self.n_file * self.n_thread) as size_pool:
            iter_map = size_pool.imap(
                self._fetch_sizes, zip(self.urls, self.filenames))
            if self.report:
                pb = tqdm(total=len(urls), unit='URL')
            for size in iter_map:
                self.batch_size += size
                if self.report:
                    pb.update()
            if self.report:
                pb.close()

    def _download(self, fd):
        try:
            fd.run()
        except Exception as e:
            self.errors.append((fd.url, fd.file_dest))
            if self.report:
                print("@[{}]:\n{}".format(fd.file_dest, e))

    def _fetch_sizes(self, args):
        url, filename = args
        fd = FileDownloader(url, self.file_dest, filename,
                            self.n_thread, self._q, headers=self.headers)
        if fd.filesize > 0:
            self.file_dests.append(fd.filename)
            self.downloaders.append(fd)
        return fd.filesize

    def run(self):

        # Prepare report
        if self.report:
            reporter = threading.Thread(
                target=report_download_queue, args=(self._q, self.batch_size))
            reporter.start()

        # Start download
        pool = ThreadPool(self.n_file)
        pool.map(self._download, self.downloaders)

        # Wait until downloaded
        pool.close()
        pool.join()
        if self.report:
            self._q.put("DONE")  # Force-close the reporter
            reporter.join()

        # Error ouput can be fed back into input
        if len(self.errors) > 0:
            with open('ctholly.errors', 'a') as f:
                f.write('error\n')
                for error in self.errors:
                    f.write(error[0] + ' ' + error[1] + '\n')
            if self.report:
                print(len(self.errors), ' errors.')
