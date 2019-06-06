import os
import re
import shutil
import requests
from PIL import Image
from requests.adapters import HTTPAdapter
from rfc6266 import parse_headers
from tqdm import tqdm
from urllib3.util.retry import Retry
from multiprocessing import Pool
from os.path import getsize, isfile, join
from urllib.parse import urlparse, urlsplit


# https://www.peterbe.com/plog/best-practice-with-retries-with-requests
def retry_session(
        retries=3,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504),
        session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def join_files(dest_file, src_files, verbose=True):
    if verbose:
        print(f"Joining to {dest_file}")
    for src_file in src_files:
        with open(dest_file, "ab") as file:
            with open(src_file, "rb") as content:
                file.write(content.read())
        os.remove(src_file)


def get_file_info(url, input_header=None):
    header = get_header(url, input_header or {})
    filesize = int(header["content-length"])
    filename = get_filename(url, header)
    accept_ranges = header.get("Accept-Ranges") == "bytes"
    return filename, filesize, accept_ranges


def get_filename(url, header):
    try:
        filename = parse_headers(header.get("content-disposition"))
        filename = filename.filename_unsafe
        assert filename is not None
    except AssertionError:
        filename = get_filename_from_url(url)
    return filename


def get_header(url, headers):
    session = retry_session()
    header = session.head(url, headers=headers).headers
    return header


def get_filename_from_url(url):
    url_parts = urlsplit(url)
    if "url=" not in url_parts.query:
        filename = url_parts.path.split('/')[-1]
    else:
        filename = re.findall(r"url=(.+?)[\?$]", url_parts.query)[0]
    filename = requests.utils.unquote(filename)
    return filename


def get_fileext_from_url(url):
    filename = get_filename_from_url(url)
    fileext = os.path.splitext(filename)[1]
    return fileext


def split_index(n_items, n_parts):
    if (n_items == 0) or (n_parts == 0):
        yield (0, 0)
        return
    part_size = n_items // n_parts
    for i in range(n_parts - 1):
        start = part_size * i
        end = part_size * (i + 1)
        yield (start, end)
    start = part_size * (n_parts - 1)
    end = n_items
    yield (start, end)


def remove_invalid_char(filename, include_path=False):
    _dict = {"/": "\\", "\\": "/"}
    not_allowed = ["?%*:|\"<>."
                   + os.sep if not include_path else _dict[os.sep]]
    return ''.join(c for c in filename if c not in not_allowed)


def fix_filename(filename):
    filename = remove_invalid_char(filename)
    if os.path.isfile(filename):
        name, ext = os.path.splitext(filename)
        i = 1
        test_name = f"{name}(1){ext}"
        while os.path.isfile(test_name):
            i += 1
            test_name = f"{name}({str(i)}){ext}"
        filename = test_name
    return filename


def get_size_downloaded(filename):
    file_size = []
    i = 0
    test_name = f"{filename}.part0"
    while os.path.isfile(test_name):
        i += 1
        file_size.append(getsize(test_name))
        test_name = f"{filename}.part{str(i)}"
    return file_size


def build_index(n, suffix="", prefix=""):
    indexes = []
    n_char = len(str(n))
    count = 0
    for _ in range(n):
        count += 1
        index = str(count)
        while len(index) < n_char:
            index = '0' + index
        indexes.append(prefix + index + suffix)
    return indexes


def build_index_filename(urls):
    filenames = []
    for (index, url) in zip(build_index(len(urls)), urls):
        filenames.append(
            index + get_fileext_from_url(url)
        )
    return filenames


def recompile_htm(fn, backup=False):
    tmp_dir = os.path.splitext(fn)[0]
    shutil.unpack_archive(fn, extract_dir=tmp_dir)
    if backup:
        os.remove(fn)
    else:
        os.rename(fn, fn + ".bak")
    files = []
    for i in os.listdir(tmp_dir):
        f = join(tmp_dir, i)
        if isfile(f):
            files.append(f)
    indexes = build_index(len(files), suffix=".jpg")
    sorted_files = sorted(files, key=lambda x: int(
        ''.join([it for it in x if it.isdigit()])))
    for (file, index) in zip(sorted_files, indexes):
        reduce_image_dimension(file)
        os.rename(file, join(tmp_dir, index))
    shutil.make_archive(tmp_dir, "zip", tmp_dir)
    shutil.rmtree(tmp_dir)


def reduce_image_dimension(fn, min_dim=720):
    img = Image.open(fn)
    width, height = img.size
    if (width <= min_dim) or (height <= min_dim):
        return
    if width < height:
        new_width = min_dim
        percent = new_width / float(width)
        new_height = int(height * percent)
    else:
        new_height = min_dim
        percent = new_height / float(height)
        new_width = int(width * percent)
    img = img.resize((new_width, new_height), Image.ANTIALIAS)
    img.save(fn)


def wrapper_reduce_image_dimension(arg):
    return reduce_image_dimension(*arg)


def reduce_images_dimension(files, min_dim=720, verbose=True):
    with Pool() as pool:
        if verbose:
            t = tqdm(total=len(files), unit="Files")
        inputs = list(zip(files, [min_dim] * len(files)))
        for _ in pool.imap_unordered(wrapper_reduce_image_dimension, inputs):
            if verbose:
                t.update()
        if verbose:
            t.close()


def get_url_domain(url):
    parsed_uri = urlparse(url)
    domain = "{uri.scheme}://{uri.netloc}/".format(uri=parsed_uri)
    return domain


def get_html_text(url):
    session = retry_session()
    page = session.get(url, verify=False, allow_redirects=True)
    html = page.text
    return html


def is_html(url):
    session = retry_session()
    headers = session.head(url).headers
    check = "text/html" in headers["content-type"]
    return check
