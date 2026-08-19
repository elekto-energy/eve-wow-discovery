#!/usr/bin/env python3
"""test_join_radec_v1.py - fixture suite for the exact geometric joiner.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

These fixtures are synthetic. They contain no archive data and make no
scientific statement. They exist to demonstrate that the joiner refuses to
pair rows that are not the same physical row, in every failure shape the
project has reason to expect.

Run:
    venv_v2\\Scripts\\python.exe tools\\test_join_radec_v1.py

All ten fixtures must pass before the joiner is used on production output.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from join_radec_v1 import join

TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_fixture_tmp")


def rec(page, y0, y1, idx, side, val="X"):
    return {
        "page": page, "row_y": [y0, y1], "row_index": idx,
        "run": "R-99", "folder": "013",
        "source_url": "http://example/%s.jpg" % page,
        "extractor": "dec_extractor_v1" if side == "dec" else "ra_extractor_v1",
        "extractor_state": "TRANSCRIBED", "extractor_value": val,
        "gate_state": "STRUCTURALLY_ADMISSIBLE", "gate_reason": "-",
        "local_sha256": "0" * 64,
        "byte_integrity": "CONSISTENT_WITH_SOURCE_PUBLISHED_CHECKSUM",
        "source_authenticity": "UNESTABLISHED",
    }


def write(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def run(name, dec_rows, ra_rows, expect):
    os.makedirs(TMP, exist_ok=True)
    d_path = os.path.join(TMP, "dec.jsonl")
    r_path = os.path.join(TMP, "ra.jsonl")
    write(d_path, dec_rows)
    write(r_path, ra_rows)
    records, summary = join(d_path, r_path)
    got = summary["verdicts"]
    ok = (all(got.get(k, 0) == v for k, v in expect.items())
          and sum(got.values()) == sum(expect.values()))
    print("%-38s %s" % (name, "PASS" if ok else "FAIL"))
    if not ok:
        print("   expected %s" % expect)
        print("   got      %s" % dict(got))
    return ok, records, summary


def main():
    d = [rec("p1", 100, 115, 0, "dec"),
         rec("p1", 120, 135, 1, "dec"),
         rec("p1", 140, 155, 2, "dec")]
    r = [rec("p1", 100, 115, 0, "ra"),
         rec("p1", 120, 135, 1, "ra"),
         rec("p1", 140, 155, 2, "ra")]
    allok = True

    ok, _, _ = run("1 perfect 1:1", d, r, {"PAIRED": 3})
    allok &= ok

    ok, _, _ = run("2 missing RA row", d,
                   [rec("p1", 100, 115, 0, "ra"), rec("p1", 140, 155, 1, "ra")],
                   {"PAIRED": 2, "UNPAIRED_DEC_ONLY": 1})
    allok &= ok

    ok, _, _ = run("3 extra RA row", d, r + [rec("p1", 160, 175, 3, "ra")],
                   {"PAIRED": 3, "UNPAIRED_RA_ONLY": 1})
    allok &= ok

    ok, _, _ = run("4 row_y shifted block", d,
                   [rec("p1", 102, 117, 0, "ra"), rec("p1", 122, 137, 1, "ra"),
                    rec("p1", 142, 157, 2, "ra")],
                   {"UNPAIRED_DEC_ONLY": 3, "UNPAIRED_RA_ONLY": 3})
    allok &= ok

    ok, _, _ = run("5 same index different row_y", d,
                   [rec("p1", 100, 115, 0, "ra"), rec("p1", 121, 136, 1, "ra"),
                    rec("p1", 140, 155, 2, "ra")],
                   {"PAIRED": 2, "UNPAIRED_DEC_ONLY": 1, "UNPAIRED_RA_ONLY": 1})
    allok &= ok

    ok, _, _ = run("6 duplicated row_y (RA)", d,
                   r + [rec("p1", 120, 135, 9, "ra", val="DUP")],
                   {"PAIRED": 2, "PAIRING_UNRESOLVED": 1})
    allok &= ok

    ok, _, summ = run("7 out-of-order rows", d,
                      [rec("p1", 140, 155, 0, "ra"), rec("p1", 100, 115, 1, "ra"),
                       rec("p1", 120, 135, 2, "ra")],
                      {"PAIRED": 3})
    allok &= ok
    dis = summ["row_index_disagreements_among_paired"]
    print("   geometry paired all three; row_index disagreements recorded: %d" % dis)
    allok &= (dis == 3)

    ok, _, _ = run("8 page only on DEC side",
                   d + [rec("p2", 100, 115, 0, "dec")], r,
                   {"PAIRED": 3, "PAGE_MISSING_ON_OTHER_SIDE": 1})
    allok &= ok

    ok, _, summ9 = run("9 page-level record skipped", d,
                       r + [{"page": "p3", "row_y": None, "row_index": None,
                             "page_state": "RA_COLUMN_UNRESOLVED"}],
                       {"PAIRED": 3})
    allok &= ok
    print("   RA page-level records skipped: %d"
          % summ9["ra_page_level_records_skipped"])
    allok &= (summ9["ra_page_level_records_skipped"] == 1)

    ok, _, _ = run("10 differing counts, exact overlap",
                   d + [rec("p1", 160, 175, 3, "dec"),
                        rec("p1", 180, 195, 4, "dec")], r,
                   {"PAIRED": 3, "UNPAIRED_DEC_ONLY": 2})
    allok &= ok

    print()
    print("ALL FIXTURES PASS" if allok else "SOME FIXTURES FAILED")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
