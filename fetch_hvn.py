import os
import utils
import sys
import re
import logging
import shutil
logging.captureWarnings(True)

from downloader import BatchDownloader


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
    else:
        title = re.findall(r"<title>(.+) \| Đọc Online</title>", html)[0][15:]
        chap_urls = re.findall(r"href=\"(.+?)\"><h2 class=\"chuong_t\"", html)
        chap_titles = re.findall(r"<h2 class=\"chuong_t\".+?>(.+?)</h2>", html)
        assert len(chap_titles) == len(chap_urls)
        print('Fetching', title, len(chap_urls))
        for url, chap in zip(chap_urls, chap_titles):
            fetch_hvn("https://hentaivn.net"+url, chap)
            for file in os.listdir(chap):
                _dest = os.path.join(title, chap)
                os.makedirs(_dest, exist_ok=True)
                shutil.copy(os.path.join(chap, file), _dest)
            shutil.rmtree(chap)


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 1:
        cmd = args[0]
    else:
        cmd = str(input('>'))
    if utils.is_html(cmd):
        fetch_hvn(cmd)
    else:
        with open(cmd, 'r') as f:
            urls = [line.strip() for line in f.readlines()]
            n = len(urls)
            for i, url in enumerate(urls):
                print('[%d/%d] %s'%(i+1, n, url))
                fetch_hvn(url)
    print("")