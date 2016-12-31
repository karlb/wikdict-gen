#!/usr/bin/env python3
# vim: set fileencoding=utf-8 :
import unittest

from parse import html_parser, clean_wiki_syntax


class TestParseHTML(unittest.TestCase):

    def test_entity(self):
        self.assertEqual(
            html_parser.parse(u'die Art und Weise des Herabhängens von Stoffen o.&nbsp;Ä.'),
            u'die Art und Weise des Herabhängens von Stoffen o.\xa0Ä.'
        )

    def test_subscript(self):
        self.assertEqual(
            html_parser.parse(u'Gruppenformel CH<sub>3</sub>–(CH<sub>2</sub>)<sub>8</sub>–</small/>COOH'),
            u'Gruppenformel CH₃–(CH₂)₈–COOH'
        )

    def test_ref(self):
        self.assertEqual(
            html_parser.parse(u'Beschlag aus Holz, Knochen oder Metall<ref name="Grabungswörterbuch">Grabungswörterbuch, Stichwort [http://ausgraeberei.de/woerterbuch/index.html?Infodeu/Riemenzunge.htm Riemenzunge]</ref> am (herabhängenden<ref name="TemporaNostra">Tempora Nostra: Mode im Hochmittelalter, Lexikon [http://www.gewandung.de/gewandung/index.php?id=lx_riemenzunge&kontextId=178&kontextNav=1 Riemenzunge]</ref>) Ende eines Gürtels, zur Verstärkung<ref name="Grabungswörterbuch" /> und Beschwerung<ref name="TemporaNostra" />'),
            u'Beschlag aus Holz, Knochen oder Metall am (herabhängenden) Ende eines Gürtels, zur Verstärkung und Beschwerung'
        )


class TestParseCleanup(unittest.TestCase):

    def test_bold_and_italics(self):
        # remove double and triple ticks, which represent italics and bold in
        # wiki syntax
        self.assertEqual(clean_wiki_syntax("Brunnen mit ''Spring''fontänen"),
                         "Brunnen mit Springfontänen")
        self.assertEqual(clean_wiki_syntax("'''V'''ereinte '''N'''ationen"),
                         "Vereinte Nationen")
        # keep single ticks
        self.assertEqual(clean_wiki_syntax("Karl's test case"),
                         "Karl's test case")


if __name__ == '__main__':
    unittest.main()
