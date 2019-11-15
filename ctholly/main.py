# coding: utf8
import logging
import os
import re
import shutil
import sys
from ctholly import utils
from ctholly.downloader import (download_manga,
                                download_file,
                                redownload_error)

logging.captureWarnings(True)


_HTM = "https://hitomi.la"


def fetch_htm(url):
    """Download single chap from HTM."""

    # Determine image server (thanks to Hentoid)
    book_id = int(str(re.findall(r"-(.+?)\.html", url)[0]).split('-')[-1])
    hostname_suffix = "a"
    number_of_frontends = 3
    hostname_prefix_base = 97
    img_prefix = "https://" + chr(hostname_prefix_base + (book_id % number_of_frontends)) + hostname_suffix
    img_prefix += ".hitomi.la/images/"

    # Get title
    url = _HTM + "/reader/" + str(book_id) + ".html"
    html = utils.get_html_text(url)
    title = re.findall(r"<title>(.+) \| Hitomi.la</title>", html)[0]
    title = utils.remove_invalid_char(title)

    # Get url of images
    json_file = "https://ltn.hitomi.la/galleries/" + str(book_id) + ".js"
    json_file = utils.get_html_text(json_file)
    filenames = re.findall(r",\"name\":\"(.+?)\",", json_file)
    hashs = re.findall(r",\"hash\":\"(.+?)\",", json_file)
    compAs = [img_hash[-1] for img_hash in hashs]
    compBs = [img_hash[-3:-1] for img_hash in hashs]
    img_urls = [img_prefix + compA + '/' + compB + '/' + img_hash + utils.extract_ext(filename)
                for compA, compB, img_hash, filename in zip(compAs, compBs, hashs, filenames)]

    # Execute download
    download_manga(url, title, img_urls)


_HVN = "https://hentaivn.net"


def fetch_hvn(url, title=None):
    """Download single-chap, one-shot or a-series from HVN.
        Deprecated. HVN is downed."""

    html = utils.get_html_text(url)

    # Try to get title for chapter
    if not title:
        title = re.findall(r"<title>(.+) Full</title>", html)

    # Yes, chapter title detected
    if len(title):

        # Get url of images
        title = title[0][16:] if len(title) == 1 else title
        img_urls = re.findall(r"<img src=\"(h.+?)\"", html)[1:]

        # Choose server for fast image load
        img_server = ''
        img_urls = [(img_server + img) for img in img_urls]

        # Execute download
        download_manga(url, title, img_urls)

    # No, series title detected
    else:

        # Get series title and chapters title
        title = re.findall(r"<title>(.+) (\[.+\])? \| Đọc Online</title>", html)
        if len(title) == 0:
            title = re.findall(r"<title>(.+) \| Đọc Online</title>", html)[0][15:]
        else:
            title = title[0][0][15:]
        title = utils.remove_invalid_char(title)
        chap_urls = re.findall(r"href=\"(.+?)\"><h2 class=\"chuong_t\"", html)
        chap_titles = re.findall(r"<h2 class=\"chuong_t\".+?>(.+?)</h2>", html)
        chap_titles = [utils.remove_invalid_char(chap_title) for chap_title in chap_titles]
        assert len(chap_titles) == len(chap_urls)
        if len(chap_titles) == 1:
            return fetch_hvn(_HVN + chap_urls[0])

        # Iterate through each chapter
        print('Fetching series: {} ({} chapters)'.format(title, len(chap_titles)))
        for url, chap in zip(chap_urls, chap_titles):

            # Download chapter
            fetch_hvn(_HVN + url, chap)

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
    else:
        download_file(url)


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
    elif cmd.endswith(".zip"):
        utils.recompile_htm(cmd, backup=False)

    # Open text file containing urls
    elif os.path.isfile(cmd):
        with open(cmd, 'r') as f:
            urls = [line.strip() for line in f.readlines()]
            if cmd == utils.ERROR_FILE:
                return redownload_error()
            else:
                n = len(urls)
                for i, cmd in enumerate(urls):
                    print(f"[{i + 1}/{n}] {cmd}")
                    main(cmd)

    # Recompile folder
    elif os.path.isdir(cmd):
        utils.recompile_htm(cmd)

    # Download normal file
    else:
        download_file(cmd)


if __name__ == '__main__':
    main()
    print('CTHOLLY EXIT')
