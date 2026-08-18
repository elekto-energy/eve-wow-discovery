#!/usr/bin/env python3
"""dec_validity_gate_v1.py - structural validity gate for declination values
produced by the frozen extractor dec_extractor_v1.py.

PROJECT: 043_wow_discovery (WOW v2 discovery track)
POSITION IN THE CHAIN:
    frozen OCR v1  ->  THIS GATE  ->  coordinate transform  ->  D2 eligibility

WHY THIS EXISTS
    The 84-page production pilot revealed a failure mode the development
    validation set did not contain: the extractor can emit a value that
    satisfies its own normalisation rule, and therefore reaches the
    TRANSCRIBED state, while being impossible as a sexagesimal coordinate.
    Observed examples include arcminute components of 60 or more.

    The frozen extractor was NOT modified in response. Its raw outputs must
    remain attributable to the exact instrument that was committed before
    the population was opened. This gate is a separate, later layer.

THE ONE RULE THAT MATTERS
    The gate may REJECT a value from scientific use. It may NEVER repair,
    infer, round, truncate or otherwise alter one. An arcminute component
    of 64 is not silently read as 04, 06, 44 or anything else. It is
    rejected and sent to human review with the original reading intact.

DECISIONS
    no value from the extractor            -> UNREADABLE
    value not parseable as DD MM           -> MANUAL_REVIEW_REQUIRED
    arcminute component >= 60              -> MANUAL_REVIEW_REQUIRED
    degree component outside the declared
      plausible band                       -> MANUAL_REVIEW_REQUIRED
    otherwise                              -> STRUCTURALLY_ADMISSIBLE

    STRUCTURALLY_ADMISSIBLE means only that the value is a possible
    coordinate. It says nothing about whether it is the value printed on
    the page, and nothing about D2 eligibility. Source-image verification
    and the sealed epoch transform still apply.

DEGREE BAND
    The declared plausible band is -20 to -35 degrees inclusive. It is a
    CONTROLLER-style declared choice, not a derivation: it is wide enough to
    contain every declination setting observed across the bracketed
    population with a large margin, and narrow enough to catch readings such
    as -76 or -97 that cannot belong to this material. A value rejected by
    this band is sent to review, never discarded and never corrected.

OUTPUT
    The gate emits a new field alongside the extractor's own output. The
    extractor's raw reads, normalised values and state are passed through
    unchanged so that the original evidence survives in the record.
"""
import json
import re
import sys

GATE_VERSION = "dec_validity_gate_v1"
ARCMIN_MAX = 60
DEGREE_BAND = (-35, -20)   # inclusive, declared choice

ADMISSIBLE = "STRUCTURALLY_ADMISSIBLE"
REVIEW = "MANUAL_REVIEW_REQUIRED"
UNREADABLE = "UNREADABLE"


def parse(value):
    """Return (degrees, arcminutes) or None. Never repairs."""
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*-(\d{2})\s+(\d{2})\s*", value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def gate_value(value):
    """Classify one extractor value. Returns (state, reason)."""
    if value is None:
        return UNREADABLE, "extractor produced no value"
    parsed = parse(value)
    if parsed is None:
        return REVIEW, "value does not parse as two two-digit groups"
    deg, arcmin = parsed
    if arcmin >= ARCMIN_MAX:
        return REVIEW, "arcminute component %d is not a valid sexagesimal minute" % arcmin
    if not (DEGREE_BAND[0] <= -deg <= DEGREE_BAND[1]):
        return REVIEW, "degree component -%d lies outside the declared plausible band" % deg
    return ADMISSIBLE, "value is a possible coordinate"


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
        print("usage: dec_validity_gate_v1.py EXTRACTOR_OUTPUT.json")
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
