import re

from html.parser import HTMLParser
from html.entities import name2codepoint

superscript = {
    '1': "\u00B9",
    '2': "\u00B2",
    '3': "\u00B3",
    '4': "\u2074",
    '5': "\u2075",
    '6': "\u2076",
    '7': "\u2077",
    '8': "\u2078",
    '9': "\u2079",
}

subscript = {
    '1': "\u2081",
    '2': "\u2082",
    '3': "\u2083",
    '4': "\u2084",
    '5': "\u2085",
    '6': "\u2086",
    '7': "\u2087",
    '8': "\u2088",
    '9': "\u2089",
}

ignore_tag_content = ['ref']


class MyHTMLParser(HTMLParser):
    def _flush_tag(self):
        self.output += self.tag_data
        self.tag_data = ''

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
            self.tag_data = ''

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
            c = chr(name2codepoint[name])
        except KeyError:
            c = name
        self.tag_data += c

    def parse(self, html):
        if html is None:
            return None
        self.output = ''
        self.tag_stack = []
        self.tag_data = ''

        self.feed(html)

        self._flush_tag()
        return self.output

html_parser = MyHTMLParser()


bold_and_italics = re.compile(r"'{2,3}")
noise_at_start = re.compile(r"^[:\|] ?")
double_brackets = re.compile(r"\[\[(?:[\w#]+\|)?([\w ]+)\]\]")
braces_nocat = re.compile(r"\|(?:\d+ )?{{.*nocat=1")
braces_notclosed = re.compile(r"{{[^}]+")


def clean_wiki_syntax(x):
    x = noise_at_start.sub('', x)
    x = double_brackets.sub(r'\1', x)
    x = bold_and_italics.sub('', x)
    x = braces_nocat.sub('', x)
    # remove when https://bitbucket.org/serasset/dbnary/issues/25 is fixed
    x = braces_notclosed.sub('', x)
    return x.strip()


fr_dummy_sense = re.compile(
    r"^(?:(?:traductions|sens)?.* )?[àa] (?:trier|classer)",
    re.IGNORECASE)


def is_dummy_sense(sense, lang):
    if lang == 'fr':
        return bool(fr_dummy_sense.search(sense))
    return False


def make_conjugation_cleaner(lang):
    if lang == 'de':
        pronouns = re.compile(r'^(er/sie/es|ich|du|er|sie|es|wir|ihr|sie)\s+')
        imperative_exclamation_mark = re.compile('!$')
        return lambda x: imperative_exclamation_mark.sub('', pronouns.sub('', x))
    return lambda x: x
