import os
import utils
import sys
import re
import logging
logging.captureWarnings(True)

from downloader import BatchDownloader


def fetch_htm(url):
    url = url.replace('galleries', 'reader')
    html = utils.fetch_html(url)
    title = re.findall(r"<title>(.+) \| Hitomi.la</title>", html)[0]
    res = re.findall(r"<div class=\"img-url\">//g(.+?)</div>", html)
    img_urls = ["https://ba"+s for s in res]
    bd = BatchDownloader(img_urls, title, 'numeric')
    bd.run()


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 1:
        cmd = args[0]
    else:
        cmd = str(input('>'))
    if utils.is_html(cmd):
        fetch_htm(cmd)
    elif cmd.endswith('.zip'):
        utils.recompile_htm(cmd, backup=False)
    else:
        with open(cmd, 'r') as f:
            urls = [line.strip() for line in f.readlines()]
            n = len(urls)
            for i, url in enumerate(urls):
                print('[%d/%d] %s'%(i+1, n, url))
                fetch_htm(url)
    print("")