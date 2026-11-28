# -*- coding: utf-8 -*-
"""Поиск фотографий цветов в интернете через API Википедии (один запрос на ~40 цветов)."""
import json
import urllib.parse
import urllib.request

API = "https://en.wikipedia.org/w/api.php"
UA = "FloraShopApp/1.0 (student project; python urllib)"


def fetch_photo_urls(titles, size=500):
    """titles — список названий статей. Возвращает {название: url фотографии}."""
    result = {}
    titles = [t for t in titles if t]
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        params = {
            "action": "query", "format": "json", "prop": "pageimages", "piprop": "thumbnail",
            "pithumbsize": str(size), "pilimit": "50", "redirects": "1", "titles": "|".join(chunk),
        }
        req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.load(resp)
        q = data.get("query", {})
        norm = {x["from"]: x["to"] for x in q.get("normalized", [])}
        redir = {x["from"]: x["to"] for x in q.get("redirects", [])}
        pages = {p.get("title"): p for p in q.get("pages", {}).values()}
        for t in chunk:
            cur = norm.get(t, t)
            cur = redir.get(cur, cur)
            page = pages.get(cur)
            if page and "thumbnail" in page:
                result[t] = page["thumbnail"]["source"]
    return result


if __name__ == "__main__":
    print(fetch_photo_urls(["Rose", "Tulip"]))
