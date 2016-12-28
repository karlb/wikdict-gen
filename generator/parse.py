import re

from HTMLParser import HTMLParser
from htmlentitydefs import name2codepoint

superscript = {
    '1': u"\u00B9",
    '2': u"\u00B2",
    '3': u"\u00B3",
    '4': u"\u2074",
    '5': u"\u2075",
    '6': u"\u2076",
    '7': u"\u2077",
    '8': u"\u2078",
    '9': u"\u2079",
}

subscript = {
    '1': u"\u2081",
    '2': u"\u2082",
    '3': u"\u2083",
    '4': u"\u2084",
    '5': u"\u2085",
    '6': u"\u2086",
    '7': u"\u2087",
    '8': u"\u2088",
    '9': u"\u2089",
}

ignore_tag_content = ['ref']


class MyHTMLParser(HTMLParser):
    def _flush_tag(self):
        self.output += self.tag_data
        self.tag_data = u''

    def handle_starttag(self, tag, attrs):
        self._flush_tag()
        self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        # sanity check; should be true for valid html
        if self.tag_stack and tag == self.tag_stack[-1]:
            self.tag_stack.pop()
        if tag == 'sup':
            self.tag_data = superscript.get(self.tag_data, self.tag_data)
        elif tag == 'sub':
            self.tag_data = subscript.get(self.tag_data, self.tag_data)
        elif tag in ignore_tag_content:
            self.tag_data = u''

        self._flush_tag()

    """
    def handle_comment(self, data):
        print "Comment  :", data
    def handle_charref(self, name):
        if name.startswith('x'):
            c = unichr(int(name[1:], 16))
        else:
            c = unichr(int(name))
        print "Num ent  :", c
    def handle_decl(self, data):
        print "Decl     :", data
    """

    def handle_data(self, data):
        self.tag_data += data

    def handle_entityref(self, name):
        try:
            c = unichr(name2codepoint[name])
        except KeyError:
            c = name
        self.tag_data += c

    def parse(self, html):
        if html is None:
            return None
        self.output = u''
        self.tag_stack = []
        self.tag_data = ''

        self.feed(html)

        self._flush_tag()
        return self.output

html_parser = MyHTMLParser()


bold_and_italics = re.compile(r"'{2,3}")


def clean_wiki_syntax(x):
    return bold_and_italics.sub('', x)

