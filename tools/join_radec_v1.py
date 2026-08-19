#!/usr/bin/env python3
"""join_radec_v1.py - exact geometric pairing of declination and right
ascension rows.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

WHY THIS IS STRICT
    Declination and right ascension are extracted by two separate frozen
    instruments, each of which finds its own row bands on the page. Two
    extractors can segment the same page differently, so the same row index
    can refer to different physical rows. Pairing by index alone would be
    silently wrong.

    The project has already been bitten by exactly this: a validation
    scoring harness aligned values instead of geometry and reported three
    false errors that were a one-row shift. That result was invalidated.

THE KEY
    PRIMARY:   (source_page, row_y)
    SECONDARY: row_index, recorded and compared, but never used to pair.

RULES
    same page AND identical row_y            -> PAIRED
    same page, row_y differs                 -> PAIRING_UNRESOLVED
    row_y present on one side only           -> UNPAIRED_DEC_ONLY / UNPAIRED_RA_ONLY
    row_y duplicated on either side          -> PAIRING_UNRESOLVED for all copies
    page present on one side only            -> every row PAGE_MISSING_ON_OTHER_SIDE
    differing row counts on a page           -> NOT an error in itself; each
                                                row_y is evaluated individually

    No nearest-neighbour matching.
    No cadence matching.
    No inferred offset.
    No value matching.
    No tolerance window on row_y.

    The joiner prefers to leave a hundred rows unresolved over pairing one
    physical row wrongly.

WHAT IT DOES NOT DO
    No coordinate transform. No B1 comparison. No eligibility decision.
    No scientific classification of any kind. It produces a joined record
    set and a summary; the sealed transform and the sealed bounds are
    applied afterwards, by other tools.

OUTPUT
    radec_rows_v2.jsonl  one record per row_y seen on either side, carrying
                         both sides' provenance, states and values, plus the
                         pairing verdict.
    join_summary.json    counts by verdict, per page and overall.

USAGE
    python tools\\join_radec_v1.py --dec outputs\\dec_population\\dec_rows.jsonl
                                  --ra  outputs\\ra_population\\ra_rows.jsonl
                                  --out outputs\\radec
"""
import argparse
import json
import os
import sys
from collections import defaultdict

PAIRED = "PAIRED"
UNRESOLVED = "PAIRING_UNRESOLVED"
DEC_ONLY = "UNPAIRED_DEC_ONLY"
RA_ONLY = "UNPAIRED_RA_ONLY"
PAGE_MISSING = "PAGE_MISSING_ON_OTHER_SIDE"

JOINER_VERSION = "join_radec_v1"


def row_key(rec):
    """Geometric identity of a physical row: page plus exact band."""
    ry = rec.get("row_y")
    if ry is None:
        return None
    if isinstance(ry, list):
        ry = tuple(ry)
    return (rec.get("page"), ry)


def load(path, side):
    """Load one side. Returns (by_key, duplicates, pages, skipped)."""
    by_key = {}
    duplicates = set()
    pages = set()
    skipped = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pages.add(rec.get("page"))
            key = row_key(rec)
            if key is None:
                # page-level record, for example RA_COLUMN_UNRESOLVED
                skipped += 1
                continue
            if key in by_key:
                duplicates.add(key)
            by_key[key] = rec
    return by_key, duplicates, pages, skipped


def project(rec, side):
    """Extract the fields worth carrying into the joined record."""
    if rec is None:
        return None
    out = {
        "row_index": rec.get("row_index"),
        "extractor": rec.get("extractor"),
        "extractor_sha256": rec.get("extractor_sha256"),
        "gate_sha256": rec.get("gate_sha256"),
        "extractor_state": rec.get("extractor_state"),
        "extractor_value": rec.get("extractor_value"),
        "gate_state": rec.get("gate_state"),
        "gate_reason": rec.get("gate_reason"),
        "local_sha256": rec.get("local_sha256"),
        "byte_integrity": rec.get("byte_integrity"),
        "source_authenticity": rec.get("source_authenticity"),
    }
    if side == "ra":
        out["ra_column"] = rec.get("ra_column")
    return out


def join(dec_path, ra_path):
    dec, dec_dupes, dec_pages, dec_skipped = load(dec_path, "dec")
    ra, ra_dupes, ra_pages, ra_skipped = load(ra_path, "ra")

    both_pages = dec_pages | ra_pages
    only_dec_pages = dec_pages - ra_pages
    only_ra_pages = ra_pages - dec_pages

    records = []
    counts = defaultdict(int)
    per_page = defaultdict(lambda: defaultdict(int))

    for key in sorted(set(dec) | set(ra), key=lambda k: (str(k[0]), k[1])):
        page, ry = key
        d = dec.get(key)
        r = ra.get(key)
        reason = None

        if key in dec_dupes or key in ra_dupes:
            verdict = UNRESOLVED
            reason = "row_y appears more than once on this page"
        elif d is not None and r is not None:
            verdict = PAIRED
        elif d is not None:
            if page in only_dec_pages:
                verdict, reason = PAGE_MISSING, "page absent from the RA side"
            else:
                verdict = DEC_ONLY
                reason = "no RA row with this exact row_y on this page"
        else:
            if page in only_ra_pages:
                verdict, reason = PAGE_MISSING, "page absent from the DEC side"
            else:
                verdict = RA_ONLY
                reason = "no DEC row with this exact row_y on this page"

        index_agreement = None
        if verdict == PAIRED:
            di, ri = d.get("row_index"), r.get("row_index")
            index_agreement = "AGREE" if di == ri else "DIFFER"
            if index_agreement == "DIFFER":
                reason = ("row_index differs between sides (%s vs %s); pairing "
                          "is by geometry, the index disagreement is recorded "
                          "only" % (di, ri))

        src = d if d is not None else r
        records.append({
            "page": page,
            "row_y": list(ry),
            "run": src.get("run"),
            "folder": src.get("folder"),
            "source_url": src.get("source_url"),
            "pairing_verdict": verdict,
            "pairing_reason": reason,
            "row_index_agreement": index_agreement,
            "joiner_version": JOINER_VERSION,
            "dec": project(d, "dec"),
            "ra": project(r, "ra"),
        })
        counts[verdict] += 1
        per_page[page][verdict] += 1

    summary = {
        "joiner_version": JOINER_VERSION,
        "key": "PRIMARY (source_page, row_y); row_index recorded and compared "
               "but never used to pair",
        "dec_rows_indexed": len(dec),
        "ra_rows_indexed": len(ra),
        "dec_page_level_records_skipped": dec_skipped,
        "ra_page_level_records_skipped": ra_skipped,
        "duplicate_row_y_dec": len(dec_dupes),
        "duplicate_row_y_ra": len(ra_dupes),
        "pages_dec": len(dec_pages),
        "pages_ra": len(ra_pages),
        "pages_either_side": len(both_pages),
        "pages_only_dec": sorted(p for p in only_dec_pages if p),
        "pages_only_ra": sorted(p for p in only_ra_pages if p),
        "verdicts": dict(counts),
        "row_index_disagreements_among_paired": sum(
            1 for r in records
            if r["pairing_verdict"] == PAIRED
            and r["row_index_agreement"] == "DIFFER"),
        "no_scientific_classification_performed": True,
    }
    return records, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dec", required=True)
    ap.add_argument("--ra", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    records, summary = join(args.dec, args.ra)

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    rows_path = os.path.join(out, "radec_rows_v2.jsonl")
    summary_path = os.path.join(out, "join_summary.json")

    with open(rows_path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(summary_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print("joined rows: %d" % len(records))
    for k in sorted(summary["verdicts"]):
        print("  %-28s %d" % (k, summary["verdicts"][k]))
    print("row_index disagreements among paired rows: %d"
          % summary["row_index_disagreements_among_paired"])
    print("rows file: %s" % rows_path)
    print("summary:   %s" % summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
