#!/usr/bin/env python3
# vim: set fileencoding=utf-8 :
# pylint: disable=line-too-long
import unittest

import sys
from parse import html_parser, clean_wiki_syntax, is_dummy_sense, make_inflection_cleaner


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

    def test_noise_at_start(self):
        self.assertEqual(
            clean_wiki_syntax(": Gesamtheit, alle "),
            "Gesamtheit, alle")

    def test_double_brackets(self):
        self.assertEqual(
            clean_wiki_syntax("Qui est en [[âge]] de se [[marier]]"),
            "Qui est en âge de se marier")
        self.assertEqual(
            clean_wiki_syntax("Voir [[sauter#fr|sauter]]"),
            "Voir sauter")
        self.assertEqual(
            clean_wiki_syntax("[[bloc de béton]]"),
            "bloc de béton")
        self.assertEqual(
            clean_wiki_syntax("[[ojentaa]] ([[käsi|käte]][[-nsa|nsä]])"),
            "ojentaa (kätensä)")

    def test_dummy_sense(self):
        dummies = [
            'Traductions à trier suivant le sens',
            'Traductions à trier suivant le sens.',
            'Traductions à trier',
            'À trier',
            'à trier',
            'Traduction à trier',
            'Traductions à vérifier et à trier',
            'À trier selon le sens',
            'Traductions à classer d’après le sens',
            'traduction à classer',
            'A trier',
            'Autres sens à trier',
        ]
        for d in dummies:
            self.assertEqual(is_dummy_sense(d, 'fr'), True, d)
        self.assertEqual(is_dummy_sense('Le sense', 'fr'), False)

    def test_braces_nocat(self):
        self.assertEqual(
            clean_wiki_syntax("Saillir une femelle (la féconder).|9 {{trans|nocat=1"),
            "Saillir une femelle (la féconder).")


class TestCleanInflection(unittest.TestCase):

    def test_de(self):
        cleaner = make_inflection_cleaner('de')
        self.assertEqual(cleaner('er/sie/es geht'), 'geht')
        self.assertEqual(cleaner('wirf!'), 'wirf')
        self.assertEqual(cleaner('die Bäume'), 'Bäume')


if __name__ == '__main__':
    unittest.main()
