#!/usr/bin/env python3

import os
import sqlite3
from datetime import date

main_db = sqlite3.connect('dictionaries/wdweb/wikdict.sqlite3')
main_db.row_factory = sqlite3.Row
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


def make_sitemap(pair, lang):
    cur = sqlite3.connect('dictionaries/processed/%s.sqlite3' % lang).cursor()
    cur.execute('SELECT vocable FROM importance ORDER BY score DESC LIMIT 100')
    sorted_pair = '-'.join(sorted(pair.split('-')))
    urls = ''.join(
        '''
        <url>
            <loc>https://www.wikdict.com/{}/{}</loc>
            <changefreq>monthly</changefreq>
        </url>
        '''.format(sorted_pair, vocable.split('/')[1])
        for (vocable,) in cur
    )
    filename = 'sitemap/{}.xml'.format(pair)
    with open(filename, 'w') as f:
        f.write(sitemap_tmpl.format(urls))
    return filename


def make_sitemap_index(sitemaps):
    urls = ''.join(
        '''
        <sitemap>
            <loc>https://www.wikdict.com/static/{}</loc>
            <lastmod>{}</lastmod>
        </sitemap>
        '''.format(url, date.today())
        for url in sitemaps
    )
    with open('sitemap/index.xml', 'w') as f:
        f.write(sitemap_index_tmpl.format(urls))


def main():
    os.makedirs('sitemap', exist_ok=True)
    cur = main_db.cursor()
    cur.execute("SELECT * FROM lang_pair")
    sitemaps = []
    for row in cur:
        pair = row['from_lang'] + '-' + row['to_lang']
        print(pair)
        sitemaps.extend([
            make_sitemap(pair, row['from_lang']),
            make_sitemap(pair, row['to_lang'])
        ])
    make_sitemap_index(sitemaps)

main()
