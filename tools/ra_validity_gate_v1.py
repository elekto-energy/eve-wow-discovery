#!/usr/bin/env python3
"""ra_validity_gate_v1.py - structural validity gate for right ascension
values produced by ra_extractor_v1.py.

PROJECT: 043_wow_discovery (WOW v2 discovery track)
POSITION IN THE CHAIN:
    frozen RA OCR v1  ->  THIS GATE  ->  paired with frozen DEC v1 output
    ->  FK4(B1950) to FK5(J2000) per row  ->  D2 eligibility

WHY A SEPARATE GATE
    The declination gate exists because the declination extractor was shown
    in production to emit syntactically valid but impossible coordinate
    values. The same class of failure is expected here, so right ascension
    gets its own structural gate rather than inheriting declination
    semantics by habit. The valid ranges are different: hours run 0 to 23,
    minutes and seconds 0 to 59.

THE ONE RULE THAT MATTERS
    The gate may REJECT a value from scientific use. It may NEVER repair,
    infer, round, truncate or otherwise alter one. A seconds component of
    75 is not read as 15, 45 or 05. It is rejected and sent to human
    review with the original reading intact.

DECISIONS
    no value from the extractor            -> UNREADABLE
    value not parseable as HH MM SS        -> MANUAL_REVIEW_REQUIRED
    hours outside 0..23                    -> MANUAL_REVIEW_REQUIRED
    minutes outside 0..59                  -> MANUAL_REVIEW_REQUIRED
    seconds outside 0..59                  -> MANUAL_REVIEW_REQUIRED
    otherwise                              -> STRUCTURALLY_ADMISSIBLE

    STRUCTURALLY_ADMISSIBLE means only that the value is a possible right
    ascension. It says nothing about whether it is the value printed on the
    page, and nothing about D2 eligibility.

WHAT IS DELIBERATELY NOT DONE HERE
    The records follow a regular cadence in time, so a neighbouring-row
    consistency check would catch further errors. That check is NOT part of
    this gate. A cadence rule that rejected values would be a new
    analytical criterion, and one that corrected them would be repair.
    If such a check is wanted it becomes a separate, declared QA layer with
    its own record.

NOTE ON STATE COLLAPSE
    The declination gate maps a missing value to UNREADABLE regardless of
    whether the extractor found no ink or its variants disagreed, which
    merges two epistemically different states. This gate has the same
    behaviour, deliberately, so the two fields stay comparable. Downstream
    work must therefore always read the PAIR (extractor_state, gate_state)
    and never gate_state alone when asking why a value is missing.
"""
import json
import re
import sys

GATE_VERSION = "ra_validity_gate_v1"
HOUR_MAX = 23
MIN_MAX = 59
SEC_MAX = 59

ADMISSIBLE = "STRUCTURALLY_ADMISSIBLE"
REVIEW = "MANUAL_REVIEW_REQUIRED"
UNREADABLE = "UNREADABLE"


def parse(value):
    """Return (hours, minutes, seconds) or None. Never repairs."""
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*(\d{2})\s+(\d{2})\s+(\d{2})\s*", value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def gate_value(value):
    """Classify one extractor value. Returns (state, reason)."""
    if value is None:
        return UNREADABLE, "extractor produced no value"
    parsed = parse(value)
    if parsed is None:
        return REVIEW, "value does not parse as three two-digit groups"
    h, m, s = parsed
    if h > HOUR_MAX:
        return REVIEW, "hour component %d is outside 0 to 23" % h
    if m > MIN_MAX:
        return REVIEW, "minute component %d is outside 0 to 59" % m
    if s > SEC_MAX:
        return REVIEW, "second component %d is outside 0 to 59" % s
    return ADMISSIBLE, "value is a possible right ascension"


def gate_rows(rows):
    """Apply the gate to extractor output for one page.

    The extractor's own fields are passed through unchanged. Only the
    gate_state, gate_reason and gate_version fields are added.
    """
    out = []
    for r in rows:
        state, reason = gate_value(r.get("value"))
        item = dict(r)
        item["gate_state"] = state
        item["gate_reason"] = reason
        item["gate_version"] = GATE_VERSION
        out.append(item)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: ra_validity_gate_v1.py EXTRACTOR_OUTPUT.json")
        return 2
    data = json.load(open(sys.argv[1]))
    if isinstance(data, dict):
        result = {k: gate_rows(v) for k, v in data.items()}
    else:
        result = gate_rows(data)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
