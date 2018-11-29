import os
import utils
import sys
import re
import logging
import shutil
logging.captureWarnings(True)

from downloader import (BatchDownloader, download_from_url)


def download_manga(title, img_urls):
    """The process of downloading a manga."""
    
    print('Fetching {} ({})...'.format(title, len(img_urls)))
    bd = BatchDownloader(img_urls, title, 'numeric', n_thread=4, n_file=8)
    utils.clear_lines(2)
    print('Downloading {} ({})...'.format(title, len(img_urls)))
    bd.run()
    utils.clear_lines(2)
    print('Cropping images to 720p...')
    utils.crop_imgs(bd.file_dests)
    utils.clear_lines(2)


_HTM = "https://hitomi.la"
def fetch_htm(url):
    """Download single manga HTM."""

    # Determine image server (thanks to Hentoid)
    url = url.replace('galleries', 'reader')
    book_id = int(re.findall(r"reader/(.+).html", url)[0][-1])
    if book_id == 1:
        book_id = 0
    IMG_PREFIX = "https://"+ ("a" if (book_id % 2 == 0) else "b") + "a"

    # Get title
    html = utils.fetch_html(url)
    title = re.findall(r"<title>(.+) \| Hitomi.la</title>", html)[0]

    # Get url of images
    res = re.findall(r"<div class=\"img-url\">//g(.+?)</div>", html)
    img_urls = [IMG_PREFIX + s for s in res]

    # Execute download
    download_manga(title, img_urls)


_HVN = "https://hentaivn.net"
def fetch_hvn(url, title=None):
    """Download single-chap, one-shot or a-series from HVN."""

    html = utils.fetch_html(url)

    # Try to get title for chapter
    if not title:
        title = re.findall(r"<title>(.+) Full</title>", html)
    
    # Yes, chapter title detected
    if len(title):

        # Get url of images
        title = title[0][16:] if len(title)==1 else title
        img_urls = re.findall(r"<img src=\"(h.+?)\"", html)[1:]

        # Execute download
        download_manga(title, img_urls)

    # No, series title detected
    else:

        # Get series title and chapters title
        title = re.findall(r"<title>(.+)\[.+\] \| Đọc Online</title>", html)[0][15:]
        chap_urls = re.findall(r"href=\"(.+?)\"><h2 class=\"chuong_t\"", html)
        chap_titles = re.findall(r"<h2 class=\"chuong_t\".+?>(.+?)</h2>", html)
        assert len(chap_titles) == len(chap_urls)

        # Iterate through each chapter
        print('Fetching series: {} ({} chapters)'.format(title, len(chap_titles)))
        for url, chap in zip(chap_urls, chap_titles):

            # Download chapter
            fetch_hvn(_HVN+url, chap)

            # Move chapter to series folder
            for file in os.listdir(chap):
                _dest = os.path.join(title, chap)
                os.makedirs(_dest, exist_ok=True)
                shutil.copy(os.path.join(chap, file), _dest)
            shutil.rmtree(chap)


def fetch(url):
    """Download from supported manga sites."""

    if url.startswith(_HVN):
        fetch_hvn(url)
    elif url.startswith(_HTM):
        fetch_htm(url)


def main(cmd=None):
    """Main stuff."""

    # Get command from user
    if cmd is None:
        args = sys.argv[1:]
        if len(args) == 1:
            cmd = args[0]
        else:
            cmd = str(input('> '))
    
    # Process single url
    if utils.is_html(cmd):
        fetch(cmd)

    # Recompile zip file (deprecated)
    elif cmd.endswith('.zip'): 
        utils.recompile_htm(cmd, backup=False)

    # Open text file containing urls
    elif os.path.isfile(cmd): 
        with open(cmd, 'r') as f:
            cmds = [line.strip() for line in f.readlines()]
            n = len(cmds)
            for i, cmd in enumerate(cmds):
                print('[%d/%d] %s'%(i+1, n, cmd))
                main(cmd)
    
    # Download normal file
    else:
        download_from_url(cmd)


if __name__ == '__main__':
    main()


print('CTHOLLY EXIT')