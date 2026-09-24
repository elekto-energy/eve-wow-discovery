#!/usr/bin/env python3
"""mk_b1_review_prereg_v1.py - materialise exact Class-2 and Class-3
membership for the B1 review, before any new source image is opened.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

This script reads b1_rows_v1.jsonl and writes the preregistration artifact.
It renders nothing and opens no page image. Its output fixes the membership
lists and their hashes so that the review cannot later be redefined around
whatever the images turn out to show.

CLASS DEFINITIONS, fixed here
    Class 2: rows whose stored declination value occurs fewer than 10 times
             among the rows inside the sealed B1 window.
    Class 3: rows on a source page contributing 3 or fewer such rows.

Both are computed over the CURRENTLY ESTABLISHED PAIRED SUBSET only.

ALREADY REVIEWED
    013-063 row 27 and 013-193 row 85 were verified in class 1 and both
    proved to be transcription errors. They generated the hypotheses under
    test and are EXCLUDED from the new holdout so that the test is not
    scored on the observations that produced it.

USAGE
    python tools\\mk_b1_review_prereg_v1.py --rows outputs\\b1\\b1_rows_v1.jsonl
                                            --out research\\v2_b1
"""
import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict

CLASS2_DEC_MAX_OCCURRENCES = 10      # fewer than this
CLASS3_PAGE_MAX_HITS = 3             # at most this
ALREADY_REVIEWED = [("013-063", 27), ("013-193", 85)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src = os.path.abspath(args.rows)
    inside = []
    with open(src, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("b1_state") == "INSIDE_SEALED_B1":
                inside.append(rec)

    dec_counts = Counter(r["dec_printed_b1950"] for r in inside)
    page_counts = Counter(r["page"] for r in inside)

    def key(r):
        return "%s|%d" % (r["page"], r["row_id"])

    class2 = [r for r in inside
              if dec_counts[r["dec_printed_b1950"]] < CLASS2_DEC_MAX_OCCURRENCES]
    class3 = [r for r in inside
              if page_counts[r["page"]] <= CLASS3_PAGE_MAX_HITS]

    c2 = {key(r) for r in class2}
    c3 = {key(r) for r in class3}
    reviewed = {"%s|%d" % (p, i) for p, i in ALREADY_REVIEWED}

    union = c2 | c3
    inter = c2 & c3
    c2_new = sorted(c2 - reviewed)
    c3_new = sorted(c3 - reviewed)
    union_new = sorted(union - reviewed)

    def detail(keys):
        out = []
        idx = {key(r): r for r in inside}
        for k in keys:
            r = idx[k]
            out.append({
                "page": r["page"], "row_id": r["row_id"], "run": r["run"],
                "canonical_y": r.get("canonical_y"),
                "stored_ra_b1950": r["ra_printed_b1950"],
                "stored_dec_b1950": r["dec_printed_b1950"],
                "dec_value_occurrences_in_b1": dec_counts[r["dec_printed_b1950"]],
                "page_b1_hits": page_counts[r["page"]],
                "dec_j2000_arcmin": r.get("dec_j2000_arcmin"),
                "distance_to_nearest_edge_arcmin": r.get("distance_to_nearest_edge_arcmin"),
                "in_class_2": key(r) in c2,
                "in_class_3": key(r) in c3,
                "local_sha256": r.get("local_sha256"),
                "source_url": r.get("source_url"),
            })
        return out

    rows_to_review = detail(union_new)
    rows_blob = json.dumps(rows_to_review, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    rows_hash = hashlib.sha256(rows_blob).hexdigest()

    prereg = {
        "artifact": "B1_REVIEW_PREREGISTRATION_v1",
        "artifact_kind": "operational_pre_registration",
        "project": "043_wow_discovery",
        "record_version": 1,
        "created_utc": "2026-09-24",
        "pre_seal_status": "OPERATIONAL-WORK-RECORD-NOT-FOR-SEALING",
        "status_semantics": "No field named status. Written before any new source image is opened.",
        "written_before_any_new_image_opened": "YES",
        "input": {
            "file": src,
            "sha256": hashlib.sha256(open(src, "rb").read()).hexdigest(),
            "rows_inside_sealed_b1": len(inside),
            "distinct_pages": len(page_counts),
            "distinct_dec_values": len(dec_counts),
        },
        "class_definitions": {
            "class_2": "stored declination value occurs fewer than %d times among rows inside the sealed B1 window" % CLASS2_DEC_MAX_OCCURRENCES,
            "class_3": "source page contributes at most %d rows inside the sealed B1 window" % CLASS3_PAGE_MAX_HITS,
            "scope": "CURRENTLY_ESTABLISHED_PAIRED_SUBSET only",
        },
        "counts": {
            "class_2_total": len(c2),
            "class_3_total": len(c3),
            "intersection_total": len(inter),
            "union_total": len(union),
            "already_reviewed_in_union": len(union & reviewed),
            "class_2_new": len(c2_new),
            "class_3_new": len(c3_new),
            "union_new": len(union_new),
        },
        "already_reviewed_excluded": {
            "rows": ["%s row %d" % (p, i) for p, i in ALREADY_REVIEWED],
            "why": "Both were verified in class 1 and both proved to be transcription errors. They generated the hypotheses under test, so scoring them again would score the test on the observations that produced it.",
        },
        "hypotheses": {
            "H2": {
                "statement": "Rare stored declination values, fewer than 10 occurrences in the B1 subset, carry elevated transcription and false-B1-membership risk.",
                "state_before_review": "NOT_ESTABLISHED",
                "scored_on": "class 2 new rows only",
            },
            "H3": {
                "statement": "Source pages producing 3 or fewer B1 rows carry elevated transcription and false-B1-membership risk.",
                "state_before_review": "NOT_ESTABLISHED",
                "scored_on": "class 3 new rows only",
            },
            "kept_separate": "The two populations overlap. They are scored separately so that it is afterwards clear which signal carried any result.",
        },
        "per_row_outcome_states": {
            "SOURCE_CONFIRMED": "stored right ascension and declination match the source image sufficiently to preserve the stored coordinate",
            "TRANSCRIPTION_ERROR_B1_CHANGING": "the source image establishes that a stored value is wrong AND correction changes B1 membership",
            "TRANSCRIPTION_ERROR_NON_B1_CHANGING": "an established transcription error whose correction does not change B1 membership",
            "NOT_ESTABLISHED": "the source image cannot support a reliable reading",
        },
        "reading_rule": {
            "primary": "The verdict rests on the source image alone.",
            "context": "Neighbouring rows may be cited as contextual support only. They may never override an ambiguous source image, and no cadence-based reconstruction may substitute for source evidence.",
            "correction": "Where a correction is established, the corrected B1950 pair is converted with the sealed WOW v1 tool, unmodified, and the resulting B1 membership is recorded.",
            "no_changes_during_review": "No extraction code, gate, segmenter or stored row is altered during the review.",
        },
        "pre_existing_context": {
            "013-455": "A prior constant-test sample found this page blank in the measured mid-page band. This is recorded as pre-existing context only. It does not alter membership, the reading rule or any verdict.",
        },
        "membership_hash": {
            "rows_to_review_sha256": rows_hash,
            "covers": "the union of class 2 and class 3, excluding already reviewed rows",
        },
        "what_this_cannot_establish": [
            "Any error rate for the full 11718 row population.",
            "That frequency is a valid risk measure outside these two classes.",
            "Anything about the 138 RA_COLUMN_UNRESOLVED pages.",
        ],
        "rows_to_review": rows_to_review,
    }

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "B1_REVIEW_PREREGISTRATION_v1.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(prereg, f, indent=2)
        f.write("\n")

    print("rows inside sealed B1 : %d" % len(inside))
    print("class 2 total         : %d" % len(c2))
    print("class 3 total         : %d" % len(c3))
    print("intersection          : %d" % len(inter))
    print("union                 : %d" % len(union))
    print("already reviewed      : %d" % len(union & reviewed))
    print("class 2 new           : %d" % len(c2_new))
    print("class 3 new           : %d" % len(c3_new))
    print("UNION NEW TO REVIEW   : %d" % len(union_new))
    print("membership sha256     : %s" % rows_hash)
    print("written: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
