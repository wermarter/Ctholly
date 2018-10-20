import utils
import re


url = "https://hitomi.la/galleries/1093121.html"
url = url.replace('galleries', 'reader')
html = utils.fetch_html(url)
res = re.findall("<div class=\"img-url\">//g(.+?)</div>", html)
res = ["aa"+s for s in res]
title = re.findall("<title>(.+) \| Hitomi.la</title>", html)[0]
print(title)
