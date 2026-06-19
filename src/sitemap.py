#!/usr/bin/env python3

import os
import sqlite3
from contextlib import closing
from datetime import date

sitemap_tmpl = """
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{}
</urlset>
""".strip()
sitemap_index_tmpl = """
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{}
</sitemapindex>
""".strip()


def make_sitemap(pair):
    with closing(sqlite3.connect("dictionaries/generic/%s.sqlite3" % pair)) as conn:
        rows = conn.execute(
            "SELECT written_rep FROM translation WHERE importance > 4 ORDER BY importance * score DESC LIMIT 100;"
        ).fetchall()
    sorted_pair = "-".join(sorted(pair.split("-")))
    urls = "".join(
        """
        <url>
            <loc>https://www.wikdict.com/{}/{}</loc>
            <changefreq>monthly</changefreq>
        </url>
        """.format(sorted_pair, written_rep)
        for (written_rep,) in rows
    )
    filename = "sitemap/{}.xml".format(pair)
    with open(filename, "w") as f:
        f.write(sitemap_tmpl.format(urls))
    return filename


def make_sitemap_index(sitemaps):
    urls = "".join(
        """
        <sitemap>
            <loc>https://www.wikdict.com/static/{}</loc>
            <lastmod>{}</lastmod>
        </sitemap>
        """.format(url, date.today())
        for url in sitemaps
    )
    with open("sitemap/index.xml", "w") as f:
        f.write(sitemap_index_tmpl.format(urls))


def main():
    os.makedirs("sitemap", exist_ok=True)
    with closing(sqlite3.connect("dictionaries/wdweb/wikdict.sqlite3")) as main_db:
        main_db.row_factory = sqlite3.Row
        cur = main_db.cursor()
        cur.execute("SELECT * FROM lang_pair")
        sitemaps = []
        for row in cur.fetchall():
            pair = row["from_lang"] + "-" + row["to_lang"]
            print(pair)
            sitemaps.append(make_sitemap(pair))
    make_sitemap_index(sitemaps)


if __name__ == "__main__":
    main()
