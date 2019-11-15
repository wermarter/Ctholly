import pickle
import os
import threading
from multiprocessing.dummy import Pool as ThreadPool
from queue import Queue
from tqdm import tqdm
from ctholly import utils


def download_file(url):
    downloader = FileDownloader(url, n_thread=16)
    downloader.run()


def download_manga(url, title, img_urls):
    print(f"Fetching {title} ({len(img_urls)})...")
    bd = BatchDownloader(img_urls, title, 'numeric',
                         n_thread=1, n_file=16, headers={'referer': url})
    print(f"Downloading {title} ({len(img_urls)})...")
    bd.run()
    print("Cropping images...")
    utils.reduce_images_dimension(bd.file_dests, 720)


def redownload_error():
    with open(utils.ERROR_FILE, "rb") as f:
        errors = pickle.load(f)
    print(f"Retrying failed downloads ({len(errors)})...")
    filenames = []
    for downloader in errors:
        downloader.report = True
        downloader.n_thread = 1
        downloader.run()
        filenames.append(downloader.filename)
    print("Cropping images...")
    utils.reduce_images_dimension(filenames, 720)


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
        self.setName(filename)

    def try_to_get(self):
        session = utils.retry_session()
        response = session.get(self.url, stream=True, headers=self.headers,
                               verify=False, allow_redirects=True)
        return response

    def run(self):
        response = self.try_to_get()
        with open(self.filename, "ab") as out_file:
            for chunk in response.iter_content(1024 * 1024):
                out_file.write(chunk)
                self.report_queue.put((self.filename, len(chunk)))


class FileDownloader(threading.Thread):
    def __init__(self, url,
                 directory='.',
                 filename=None,
                 n_thread=8,
                 report=True,
                 resume_download=True,
                 headers=None):
        super().__init__()

        # Report can be handled externally by assigning a Queue to it
        if type(report) == Queue:
            self._q = report
            self.report = False
        else:
            self.report = report
            self._q = Queue()

        # Check for multithread support
        self.headers = headers or {}
        _filename, filesize, accept_range = utils.get_file_info(
            url, input_header=self.headers)
        multithread = accept_range and filesize
        if (not multithread) and (n_thread > 1):
            n_thread = 1
            if self.report:
                print("[WARN] Multithread downloading not supported")

        # Preprocess file destination
        directory = os.path.normpath(directory)
        os.makedirs(directory, exist_ok=True)
        filename = utils.fix_filename(filename or _filename)
        filename = os.path.join(directory, filename)
        start_pos = utils.get_size_downloaded(filename)

        # Download resumption
        if resume_download:
            if len(start_pos) == 0:
                self.start_pos = [0] * n_thread
            elif (start_pos[0] != 0) and (len(start_pos) > 1):
                if self.report:
                    print("Found", len(start_pos),
                          "downloaded parts. Resuming...")
                self.start_pos = start_pos
                n_thread = len(start_pos)

        self.filename = filename
        self.url = url
        self.filesize = filesize
        self.n_thread = n_thread
        self.multithread = multithread
        self.setName(filename)
        self.n_run = 0

    def run(self):
        self.n_run += 1
        download_threads = []
        part_names = []
        for i, (start, end) in enumerate(
                utils.split_index(self.filesize, self.n_thread)):
            if self.multithread:
                self.headers.update(
                    {"Range": f"bytes={self.start_pos[i] + start}-{end - 1}"})
            part_name = f"{self.filename}.part{i}"
            part_names.append(part_name)
            _thread = DownloadThread(
                self._q, self.url, part_name, self.headers)
            _thread.start()
            download_threads.append(_thread)

        # Report progress
        if self.report:
            report_thread = threading.Thread(
                target=report_download_queue,
                args=(self._q, self.filesize - sum(self.start_pos)))
            report_thread.start()

        # Wait for download to finish
        for _thread in download_threads:
            _thread.join()
        if self.report:
            self._q.put('DONE')
            report_thread.join()

        # Join downloaded parts of file
        utils.join_files(self.filename, part_names, self.report)

        # Filesize check
        if not self._check_filesize():
            if self.report:
                print(f"Size mismatched. Retrying...")
            if self.n_run < 3:
                return self.run()
            else:
                raise Exception("Cannot fully download this file.")

    def _check_filesize(self):
        actual_size = os.path.getsize(self.filename)
        if actual_size != self.filesize:
            os.remove(self.filename)
            return False
        else:
            return True


class BatchDownloader(threading.Thread):
    def __init__(self, urls,
                 directory='.',
                 filenames=None,
                 n_thread=4,
                 n_file=4,
                 report=True,
                 headers=None):
        super().__init__()

        # Filenames preprocessing
        if filenames is None:
            filenames = [None] * len(urls)
        elif filenames == "numeric":
            filenames = utils.build_index_filename(urls)

        # Report can be handled externally by assigning a Queue to it
        if type(report) == Queue:
            self._q = report
            self.report = False
        else:
            self._q = Queue()
            self.report = report

        self.n_thread = n_thread
        self.n_file = n_file
        self.urls = urls
        self.directory = directory
        self.file_dests = []
        self.errors = Queue()
        self.filenames = filenames
        self.downloaders = []
        self.batch_size = 0
        self.headers = headers
        self._init_downloaders()

    def _init_downloaders(self):
        # with ThreadPool(self.n_file * self.n_thread) as size_pool:
        with ThreadPool(2) as size_pool:
            iter_map = size_pool.imap(
                self._fetch_sizes, zip(self.urls, self.filenames))
            if self.report:
                pb = tqdm(total=len(self.urls), unit="URL")
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
            self.errors.put(fd)
            self.file_dests.remove(fd.filename)
            os.remove(fd.filename)
            if self.report:
                print(f"@[{fd.filename}]:\n{e}")

    def _fetch_sizes(self, args):
        url, filename = args
        fd = FileDownloader(url, self.directory, filename,
                            self.n_thread, self._q, headers=self.headers)
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
            self._q.put("DONE")
            reporter.join()

        # Error ouput can be fed back into input
        errors = []
        while not self.errors.empty():
            errors.append(self.errors.get())

        if len(errors) > 0:
            with open(utils.ERROR_FILE, "wb") as f:
                pickle.dump(errors, f)
            if self.report:
                print(f"There are {errors} errors.")
                prompt = input("Do you want to retry? ")
                if prompt.upper().startswith('Y'):
                    redownload_error()
