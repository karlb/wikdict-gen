"""Measure Wikidata P5137 concept agreement against the precision gold.

P5137 ("item for this sense") links a Wikidata lexeme sense to a concept Q-item.
Two words whose senses point at the *same* Q-item are concept-level evidence they
are translations -- independent of the dbnary edges inference uses, and
concept-disambiguated, so in principle it separates "go-walk" from "go-travel"
where string pivots leak (the gehen->aaka mechanism, scoring-improvement.md #3).

Before paying the integration cost (an external 590 MB lexeme load + a fuzzy
lemma/lang join into infer.sql), this probe answers the one never-measured
question on data we already have: does concept agreement actually predict the
precision gold's correct/incorrect labels, and does it withhold on the known
false positives? It needs no rebuild and touches nothing in the pipeline.

It (1) streams the Wikidata lexeme dump into a (lang, lemma) -> {Q-item} map for
the gold's languages, then (2) for each labelled gap-fill in
src/tests/data/precision_gold.tsv asks whether the source and target words share
a Q-item, and cross-tabulates that against the label.

Usage:
    python notes/p5137_probe.py --dump path/to/latest-lexemes.json.gz [--cache f.tsv]

The dump is Wikidata's weekly lexeme export (one JSON lexeme per line):
    https://dumps.wikimedia.org/wikidatawiki/entities/latest-lexemes.json.gz
"""

import argparse
import csv
import gzip
import json
import os
from collections import defaultdict

GOLD_PATH = os.path.join(
    os.path.dirname(__file__), "..", "src", "tests", "data", "precision_gold.tsv"
)
GOLD_LANGS = {"de", "en", "fr", "it", "sv"}


def parse_dump(path, langs):
    """Stream the lexeme dump, yielding (lang, lemma, qid) for every sense that
    carries a P5137 claim whose lexeme has a lemma in `langs`."""
    n = 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip().rstrip(",")
            if line in ("[", "]", ""):
                continue
            try:
                lex = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            if n % 200000 == 0:
                print(f"  ...{n} lexemes scanned", flush=True)
            lemmas = {
                code: l["value"]
                for code, l in (lex.get("lemmas") or {}).items()
                if code in langs
            }
            if not lemmas:
                continue
            qids = set()
            for sense in lex.get("senses") or []:
                for claim in (sense.get("claims") or {}).get("P5137", []):
                    try:
                        qids.add(claim["mainsnak"]["datavalue"]["value"]["id"])
                    except (KeyError, TypeError):
                        pass
            for code, lemma in lemmas.items():
                for qid in qids:
                    yield code, lemma, qid
    print(f"  scanned {n} lexemes total", flush=True)


def build_concept(dump, cache, langs):
    """(lang, lemma) -> set(qid), parsed from the dump or a cached TSV."""
    concept = defaultdict(set)
    if cache and os.path.exists(cache):
        print(f"loading concept cache {cache}")
        with open(cache, newline="") as f:
            for code, lemma, qid in csv.reader(f, delimiter="\t"):
                concept[(code, lemma)].add(qid)
    else:
        print(f"parsing dump {dump} (this takes a few minutes)")
        rows = list(parse_dump(dump, langs))
        for code, lemma, qid in rows:
            concept[(code, lemma)].add(qid)
        if cache:
            with open(cache, "w", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                for code, lemma, qid in rows:
                    w.writerow([code, lemma, qid])
            print(f"wrote concept cache {cache} ({len(rows)} rows)")
    print(f"concept map: {len(concept)} (lang, lemma) keys")
    return concept


def load_gold(path):
    """[(from_lang, to_lang, from_vocable, to_vocable, label, confidence)] over the
    correct/incorrect-labelled rows."""
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            label = (r.get("label") or "").strip()
            if label in ("correct", "incorrect"):
                out.append((
                    r["from_lang"], r["to_lang"], r["from_vocable"], r["to_vocable"],
                    label, (r.get("confidence") or "").strip(),
                ))
    return out


def agreement(concept, a, fv, b, tv):
    """(both_present, shares_qid) for source a:fv vs target b:tv."""
    src = concept.get((a, fv))
    tgt = concept.get((b, tv))
    if not src or not tgt:
        return False, False
    return True, bool(src & tgt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=os.path.expanduser(
        "~/code/experiments/anchor/data/latest-lexemes.json.gz"))
    ap.add_argument("--cache", default=None,
                    help="TSV cache of (lang, lemma, qid) to read/write")
    ap.add_argument("--gold", default=GOLD_PATH)
    args = ap.parse_args()

    concept = build_concept(args.dump, args.cache, GOLD_LANGS)
    gold = load_gold(args.gold)
    n_correct = sum(1 for *_, lab, _ in gold if lab == "correct")
    n_incorrect = sum(1 for *_, lab, _ in gold if lab == "incorrect")
    print(f"\ngold: {len(gold)} labelled rows ({n_correct} correct, {n_incorrect} incorrect)\n")

    # cross-tab over rows where BOTH words are in P5137 (the signal can speak)
    cells = {(lab, ag): 0 for lab in ("correct", "incorrect") for ag in (True, False)}
    present = {"correct": 0, "incorrect": 0}
    for a, b, fv, tv, label, _conf in gold:
        both, ag = agreement(concept, a, fv, b, tv)
        if both:
            present[label] += 1
            cells[(label, ag)] += 1

    print("coverage -- both words carry a P5137 sense (signal can speak):")
    print(f"  correct:   {present['correct']:4d} / {n_correct:<4d} "
          f"({present['correct']/n_correct:.1%})")
    print(f"  incorrect: {present['incorrect']:4d} / {n_incorrect:<4d} "
          f"({present['incorrect']/max(n_incorrect,1):.1%})")

    ca, cd = cells[("correct", True)], cells[("correct", False)]
    ia, id_ = cells[("incorrect", True)], cells[("incorrect", False)]
    print("\namong rows where both words are present:")
    print(f"                 agree   disagree")
    print(f"  correct        {ca:5d}   {cd:6d}")
    print(f"  incorrect      {ia:5d}   {id_:6d}")
    if ca + ia:
        print(f"  P(correct | agree)    = {ca/(ca+ia):.3f}  (n={ca+ia})")
    if cd + id_:
        print(f"  P(correct | disagree) = {cd/(cd+id_):.3f}  (n={cd+id_})")

    # known false positives: does the signal withhold (not-agree) on them?
    bad = [(a, b, fv, tv) for a, b, fv, tv, lab, conf in gold
           if lab == "incorrect" and conf == "high"]
    bad_present = bad_agree = 0
    for a, b, fv, tv in bad:
        both, ag = agreement(concept, a, fv, b, tv)
        bad_present += both
        bad_agree += ag
    print(f"\nconfirmed-bad (high-confidence FPs): {len(bad)} total")
    print(f"  both words present: {bad_present}   of which agree (signal fails): {bad_agree}")
    print(f"  signal withholds (absent or no shared concept): {len(bad) - bad_agree}")


if __name__ == "__main__":
    main()
