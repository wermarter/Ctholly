import re
import requests
import os
import sys
import string   
import shutil

from rfc6266 import parse_headers
from urllib.parse import (urlsplit, urlparse)
from os.path import (isfile, join)
from queue import Queue
from PIL import Image
from tqdm import tqdm
from multiprocessing import Pool


VALID_CHARS = "-_.()[] %s%s" % (string.ascii_letters, string.digits)


####################
# helper functions #
####################

def clear_lines(n=1):
    """Clear lines before this line."""

    sys.stdout.write("\033[K") # Clear
    for _ in range(n):
        sys.stdout.write("\033[F") # Move up
        sys.stdout.write("\033[K") # Clear


def join_files(fn, files, verbose=True):
    """Join multiple files into one file"""

    
    if verbose:
        print('Joining to', fn)
    for i in range(len(files))[1:]:
        with open(files[0], 'ab') as file, open(files[i], 'rb') as content:
            file.write(content.read())
        os.remove(files[i])
    os.rename(files[0], fn)


def get_file_info(url, max_tries=3):
    """Get filename, GzipSize and check if "Accept-Ranges" from the url."""

    count = max_tries
    while (count > 0):
        try:
            header = requests.head(url).headers
            break
        except Exception as e:
            print(e)
            count -= 1
    if count == 0:
        raise Exception("Cannot HEAD "+url)
    sz = header.get('content-length', 0)
    fn = parse_headers(header.get('content-disposition', None)).filename_unsafe
    if fn is None:
        fn = get_filename_url(url)
    return fn, int(sz), (header.get('Accept-Ranges', '')=='bytes')


def get_filename_url(url):
    """"Get filename from pure url."""

    parts = urlsplit(url)
    fn = parts.path.split('/')[-1] if not 'url=' in parts.query else re.findall(r"url=(.+?)[\?$]", parts.query)[0]
    return requests.utils.unquote(fn)


def get_fileext_url(url):
    """Get file's extension from pure url."""

    fn = get_filename_url(url)
    return os.path.splitext(fn)[1]


def split_index(n, m, start=0):
    """Return 0-based indexes pair (start, end) for splitting N items into M parts."""

    if (n==0) or (m==0):
        yield (0, 0)
        return
    part_size = (n-start) // m
    for i in range(m-1):
        yield start+part_size*i, start+part_size*(i+1)
    yield start+part_size*(m-1), n # last partition may not have the same size


def filename_check(fn, include_path=False, accept_exist=False):
    """Check for filename conflicts and fix them."""

    fn = ''.join(c for c in fn if c in VALID_CHARS+(os.sep if include_path else ""))
    if (not accept_exist) and os.path.isfile(fn):
        file_sz = os.path.getsize(fn)
        name, ext = os.path.splitext(fn)
        i = 1
        test_name = name + ' (1)' + ext
        while (os.path.isfile(test_name)):
            i += 1
            test_name = name + ' (%s)' % str(i) + ext
        fn = test_name
    if include_path:
        root_folder = os.path.split(fn)[0]
        if len(root_folder)>1:
            os.makedirs(root_folder, exist_ok=True)
    
    if accept_exist:
        if os.path.isfile(fn):
            file_sz = os.path.getsize(file_sz)
        else:
            file_sz = 0
        return fn, file_sz
    return fn


def sizeof_fmt(num, suffix='B'):
    """Format user-friendly filesize in kibibyte. (deprecated)"""

    for unit in ['','K','M','G','T']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'P', suffix)


def build_index(n, suffix="", prefix=""):
    """Build indexes 001, 002, 003..."""

    indexes = list()
    n_char = len(str(n))
    count = 0
    for _ in range(n):
        count += 1
        index = str(count)
        while (len(index) < n_char):
            index = '0' + index
        indexes.append(prefix + index + suffix)
    return indexes


def build_index_ext(urls):
    """Build a list of number-indexed files with preserved extension from urls."""
    return [(a+get_fileext_url(url)) for (a, url) in zip(build_index(len(urls)),urls)]


def recompile_htm(fn, backup=False):
    """Reindex zip file downloaded from htm.(deprecated)""" 

    tmp_dir = os.path.splitext(fn)[0]
    shutil.unpack_archive(fn, extract_dir=tmp_dir)
    if backup:
        os.remove(fn)
    else:
        os.rename(fn, fn+'.bak')
    
    files = []
    for i in os.listdir(tmp_dir):
        f = join(tmp_dir, i)
        if isfile(f):
            files.append(f)
    indexes = build_index(len(files), suffix='.jpg') #### Enhance
    sorted_files = sorted(files, key=lambda x: \
                   int(''.join([i for i in x if i.isdigit()]))) # Extract number from filename
    for (file, index) in zip(sorted_files, indexes):
        crop_to_720p(file)
        os.rename(file, join(tmp_dir, index))
    shutil.make_archive(tmp_dir, 'zip', tmp_dir)
    shutil.rmtree(tmp_dir)


def crop_to_720p(fn, min_len=720):
    """Crop an image file to the width/height of min_len."""

    img = Image.open(fn)
    width, height = img.size
    if (width <= min_len) or (height <= min_len):
        return
    if width < height:
        new_width = min_len
        percent = new_width / float(width)
        new_height = int(height * percent)
    else:
        new_height = min_len
        percent = new_height / float(height)
        new_width = int(width * percent)
    img = img.resize((new_width, new_height), Image.ANTIALIAS)
    img.save(fn)


def _crop_to_720p(arg):
    """A wrapper for crop_to_720p."""
    
    return crop_to_720p(*arg)


def crop_imgs(files, min_len=720, verbose=True):
    """Multiprocess crop images."""

    with Pool() as pool:
        if verbose:
            t = tqdm(total=len(files), unit='Files')
            inputs = list(zip(files, [min_len]*len(files)))
        for _ in pool.imap_unordered(_crop_to_720p, inputs):
            if verbose:
                t.update()
        if verbose:
            t.close()



def get_url_domain(url):
    """Get url domain from pure url."""

    parsed_uri  = urlparse(url)
    domain = '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
    return domain


def fetch_html(url, max_tries=3):
    """Fetch html string from url with max_tries times."""

    count = max_tries
    while (count>0):
        try:
            page = requests.get(url, verify=False, allow_redirects=True)
            break
        except:
            count -= 1
    if (count == 0):
        raise Exception("Cannot fetch " + url)
    output = page.text
    del page
    return output


def is_html(url, max_tries=3):
    """Check if url is html page."""

    count = max_tries
    while (count>0):
        try:
            r = requests.head(url)
            return 'text/html' in r.headers['content-type']
        except:
            count -= 1
    return False
