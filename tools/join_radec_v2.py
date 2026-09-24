#!/usr/bin/env python3
"""join_radec_v2.py - pair declination and right ascension rows through
canonical row identity.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

RELATION TO v1
    join_radec_v1 keyed on (source_page, row_y) and paired 798 rows of 82525.
    That key was wrong: row_y is a property of the column window a band was
    computed in, not of the page. The rule was right and refused to pair.
    v1 is not modified and its output stands as produced.

WHAT v2 DOES
    For each page it runs the frozen row_segmenter_v1 over the retained page
    image, obtaining canonical rows. Each stored declination row and each
    stored right ascension row is mapped into the canonical row its band
    overlaps. Pairing happens only inside a canonical row.

    No page is re-read for values. No extractor is re-run. The stored v1
    rows are used exactly as they are.

PAIRING RULES
    canonical row is CANONICAL_CLEAN, one dec row and one ra row  -> PAIRED
    canonical row is CANONICAL_AMBIGUOUS                          -> PAIRING_UNRESOLVED
    canonical row has a dec row but no ra row                     -> UNPAIRED_DEC_ONLY
    canonical row has an ra row but no dec row                    -> UNPAIRED_RA_ONLY
    stored row whose band overlaps no canonical row               -> BAND_NOT_IN_SEGMENTATION
    more than one stored row maps to one canonical row on a side  -> PAIRING_UNRESOLVED
    page image missing, or segmenter returns a page state         -> the page's rows are
                                                                     reported under that state

    No nearest neighbour. No cadence. No inferred offset. No value matching.
    No tolerance window. A canonical row that cannot say which line is which
    is left unresolved rather than resolved by choosing.

WHAT IT DOES NOT DO
    No coordinate transform, no comparison against the sealed B1 window, no
    eligibility decision, no scientific classification.

OUTPUT
    radec_rows_v3.jsonl   one record per canonical row, plus records for
                          stored rows that map to none
    join_v2_summary.json  counts by verdict and by page state

USAGE
    python tools\\join_radec_v2.py --dec outputs\\dec_population\\dec_rows.jsonl
                                  --ra  outputs\\ra_population\\ra_rows.jsonl
                                  --pages outputs\\ra_population\\pages
                                  --out outputs\\radec_v2
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import row_segmenter_v1 as SEG

PAIRED = "PAIRED"
UNRESOLVED = "PAIRING_UNRESOLVED"
DEC_ONLY = "UNPAIRED_DEC_ONLY"
RA_ONLY = "UNPAIRED_RA_ONLY"
NOT_IN_SEG = "BAND_NOT_IN_SEGMENTATION"
PAGE_IMAGE_MISSING = "PAGE_IMAGE_MISSING"

JOINER_VERSION = "join_radec_v2"


def load_side(path):
    """Group stored rows by page. Page-level records are kept separately."""
    by_page = defaultdict(list)
    page_level = defaultdict(list)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("row_y") is None:
                page_level[rec.get("page")].append(rec)
            else:
                by_page[rec.get("page")].append(rec)
    return by_page, page_level


def project(rec, side):
    if rec is None:
        return None
    out = {
        "row_index": rec.get("row_index"),
        "row_y": rec.get("row_y"),
        "extractor": rec.get("extractor"),
        "extractor_sha256": rec.get("extractor_sha256"),
        "gate_sha256": rec.get("gate_sha256"),
        "extractor_state": rec.get("extractor_state"),
        "extractor_value": rec.get("extractor_value"),
        "gate_state": rec.get("gate_state"),
        "gate_reason": rec.get("gate_reason"),
    }
    if side == "ra":
        out["ra_column"] = rec.get("ra_column")
    return out


def overlaps(band, canonical_y):
    return band[0] < canonical_y[1] and band[1] > canonical_y[0]


def join_page(page, dec_rows, ra_rows, seg_rows):
    """Map stored rows into canonical rows and decide each verdict."""
    dec_map = defaultdict(list)
    ra_map = defaultdict(list)
    dec_unmapped, ra_unmapped = [], []

    for rec in dec_rows:
        placed = False
        for i, c in enumerate(seg_rows):
            if overlaps(rec["row_y"], c["canonical_y"]):
                dec_map[i].append(rec)
                placed = True
                break
        if not placed:
            dec_unmapped.append(rec)

    for rec in ra_rows:
        placed = False
        for i, c in enumerate(seg_rows):
            if overlaps(rec["row_y"], c["canonical_y"]):
                ra_map[i].append(rec)
                placed = True
                break
        if not placed:
            ra_unmapped.append(rec)

    out = []
    for i, c in enumerate(seg_rows):
        d = dec_map.get(i, [])
        r = ra_map.get(i, [])
        reason = None
        if c["canonical_state"] == "CANONICAL_AMBIGUOUS":
            verdict = UNRESOLVED
            reason = "canonical row merges more than one printed line"
        elif len(d) > 1 or len(r) > 1:
            verdict = UNRESOLVED
            reason = ("more than one stored row maps to this canonical row "
                      "(dec %d, ra %d)" % (len(d), len(r)))
        elif len(d) == 1 and len(r) == 1:
            verdict = PAIRED
        elif len(d) == 1:
            verdict = DEC_ONLY
            reason = "no stored right ascension row in this canonical row"
        elif len(r) == 1:
            verdict = RA_ONLY
            reason = "no stored declination row in this canonical row"
        else:
            verdict = UNRESOLVED
            reason = "canonical row carries no stored row on either side"

        src = (d[0] if d else (r[0] if r else None))
        out.append({
            "page": page,
            "row_id": c["row_id"],
            "canonical_y": c["canonical_y"],
            "canonical_state": c["canonical_state"],
            "run": src.get("run") if src else None,
            "folder": src.get("folder") if src else None,
            "source_url": src.get("source_url") if src else None,
            "local_sha256": src.get("local_sha256") if src else None,
            "byte_integrity": src.get("byte_integrity") if src else None,
            "source_authenticity": src.get("source_authenticity") if src else None,
            "pairing_verdict": verdict,
            "pairing_reason": reason,
            "joiner_version": JOINER_VERSION,
            "segmenter_version": SEG.SEGMENTER_VERSION,
            "dec": project(d[0] if len(d) == 1 else None, "dec"),
            "ra": project(r[0] if len(r) == 1 else None, "ra"),
            "dec_rows_in_canonical": len(d),
            "ra_rows_in_canonical": len(r),
        })

    for rec in dec_unmapped:
        out.append({"page": page, "row_id": None, "canonical_y": None,
                    "canonical_state": None, "pairing_verdict": NOT_IN_SEG,
                    "pairing_reason": "stored declination band overlaps no canonical row",
                    "joiner_version": JOINER_VERSION,
                    "dec": project(rec, "dec"), "ra": None})
    for rec in ra_unmapped:
        out.append({"page": page, "row_id": None, "canonical_y": None,
                    "canonical_state": None, "pairing_verdict": NOT_IN_SEG,
                    "pairing_reason": "stored right ascension band overlaps no canonical row",
                    "joiner_version": JOINER_VERSION,
                    "dec": None, "ra": project(rec, "ra")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dec", required=True)
    ap.add_argument("--ra", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    dec_by_page, dec_page_level = load_side(args.dec)
    ra_by_page, ra_page_level = load_side(args.ra)
    pages = sorted(set(dec_by_page) | set(ra_by_page))
    if args.limit:
        pages = pages[:args.limit]
    print("pages to join: %d" % len(pages))
    sys.stdout.flush()

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    rows_path = os.path.join(out_dir, "radec_rows_v3.jsonl")
    summary_path = os.path.join(out_dir, "join_v2_summary.json")

    counts = defaultdict(int)
    page_states = defaultdict(int)
    canonical_states = defaultdict(int)
    done = 0
    with open(rows_path, "w", encoding="utf-8", newline="\n") as f:
        for page in pages:
            img = os.path.join(args.pages, page + ".jpg")
            if not os.path.exists(img):
                page_states[PAGE_IMAGE_MISSING] += 1
                f.write(json.dumps({"page": page, "row_id": None,
                                    "pairing_verdict": PAGE_IMAGE_MISSING,
                                    "joiner_version": JOINER_VERSION}) + "\n")
                continue
            state, ra_col, seg_rows = SEG.segment_page(img)
            if state is not None:
                page_states[state] += 1
                f.write(json.dumps({"page": page, "row_id": None,
                                    "pairing_verdict": state,
                                    "joiner_version": JOINER_VERSION}) + "\n")
                continue
            page_states["SEGMENTED"] += 1
            for c in seg_rows:
                canonical_states[c["canonical_state"]] += 1
            recs = join_page(page, dec_by_page.get(page, []),
                             ra_by_page.get(page, []), seg_rows)
            for r in recs:
                counts[r["pairing_verdict"]] += 1
                f.write(json.dumps(r) + "\n")
            done += 1
            if done % 50 == 0:
                print("  %d/%d pages" % (done, len(pages)))
                sys.stdout.flush()

    summary = {
        "joiner_version": JOINER_VERSION,
        "segmenter_version": SEG.SEGMENTER_VERSION,
        "key": "canonical row identity from row_segmenter_v1; stored bands mapped by overlap",
        "pages_considered": len(pages),
        "page_states": dict(page_states),
        "canonical_states": dict(canonical_states),
        "verdicts": dict(counts),
        "dec_page_level_records": sum(len(v) for v in dec_page_level.values()),
        "ra_page_level_records": sum(len(v) for v in ra_page_level.values()),
        "no_scientific_classification_performed": True,
    }
    with open(summary_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print("\npage states: %s" % dict(page_states))
    print("canonical states: %s" % dict(canonical_states))
    for k in sorted(counts):
        print("  %-28s %d" % (k, counts[k]))
    print("rows file: %s" % rows_path)
    print("summary:   %s" % summary_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
