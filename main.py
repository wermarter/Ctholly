import os
import utils
import sys
import re
import logging
import shutil
logging.captureWarnings(True)

from downloader import BatchDownloader

def post_processing(files):
    print('Cropping to 720p')
    for file in files:
        utils.crop_to_720p(file)

def fetch_htm(url):
    url = url.replace('galleries', 'reader')
    book_id = int(re.findall(r"reader/(.+).html", url)[0][-1])
    if book_id == 1:
        book_id = 0
    IMG_PREFIX = "https://"+ ("a" if (book_id % 2 == 0) else "b") + "a"
    html = utils.fetch_html(url)
    title = re.findall(r"<title>(.+) \| Hitomi.la</title>", html)[0]
    res = re.findall(r"<div class=\"img-url\">//g(.+?)</div>", html)
    img_urls = [IMG_PREFIX + s for s in res]
    print('Fetching', title, len(img_urls))
    bd = BatchDownloader(img_urls, title, 'numeric')
    bd.run()
    post_processing(bd.file_dests)

_HVN = "https://hentaivn.net"
def fetch_hvn(url, title=None):
    html = utils.fetch_html(url)
    if not title:
        title = re.findall(r"<title>(.+) Full</title>", html)
    if len(title):
        title = title[0][16:] if len(title)==1 else title
        img_urls = re.findall(r"<img src=\"(h.+?)\"", html)[1:]
        print('Fetching', title, len(img_urls))
        bd = BatchDownloader(img_urls, title, 'numeric')
        bd.run()
        post_processing(bd.file_dests)
    else:
        title = re.findall(r"<title>(.+) \| Đọc Online</title>", html)[0][15:]
        chap_urls = re.findall(r"href=\"(.+?)\"><h2 class=\"chuong_t\"", html)
        chap_titles = re.findall(r"<h2 class=\"chuong_t\".+?>(.+?)</h2>", html)
        assert len(chap_titles) == len(chap_urls)
        print('Fetching', title, len(chap_urls))
        for url, chap in zip(chap_urls, chap_titles):
            fetch_hvn(_HVN+url, chap)
            for file in os.listdir(chap):
                _dest = os.path.join(title, chap)
                os.makedirs(_dest, exist_ok=True)
                shutil.copy(os.path.join(chap, file), _dest)
            shutil.rmtree(chap)

def fetch(url):
    if url.startswith(_HVN):
        fetch_hvn(url)
    else:
        fetch_htm(url)

if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 1:
        cmd = args[0]
    else:
        cmd = str(input('>'))
    if utils.is_html(cmd):
        fetch(cmd)
    elif cmd.endswith('.zip'):
        utils.recompile_htm(cmd, backup=False)
    else:
        with open(cmd, 'r') as f:
            urls = [line.strip() for line in f.readlines()]
            n = len(urls)
            for i, url in enumerate(urls):
                print('[%d/%d] %s'%(i+1, n, url))
                fetch(url)
    print("DONE")