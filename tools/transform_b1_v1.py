#!/usr/bin/env python3
"""transform_b1_v1.py - epoch transform and sealed B1 comparison over the
established paired subset.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

SCOPE BOUNDARY (owner order, 2026-09-24)
    Input is exactly the rows whose pairing_verdict is PAIRED in
    radec_rows_v3.jsonl. Nothing else is consumed.

    This tool creates no pairing. It repairs nothing, infers nothing and
    reads no page. It never uses row proximity, ordering, cadence,
    interpolation, astronomical plausibility or value similarity.

    RA_COLUMN_UNRESOLVED pages are NOT consumed as paired input.

THE TRANSFORM
    The sealed WOW v1 tool 042_wow/scripts/wow2_epoch.py is imported
    UNMODIFIED and its to_j2000() is called. Before any conversion the tool
    runs that file's own selftest against the sealed OR-20 to OR-21 case;
    if the selftest fails, nothing is written.

    Why the sealed tool must be used per pair: the B1950 to J2000
    declination shift depends on right ascension. Measured with this same
    tool at one declination, the shift ran from -12.49 arcmin south at
    RA 14h45m to +16.16 arcmin north at RA 23h00m, a spread of 28.65
    arcmin across 72 percent of the sealed window, changing sign. A single
    offset is therefore never applied.

WHAT IS CONVERTED
    Only pairs where BOTH sides carry a gate-passing value:
        dec.gate_state == STRUCTURALLY_ADMISSIBLE
        ra.gate_state  == STRUCTURALLY_ADMISSIBLE
    Any other pair is reported with its reason and never converted.

    Conversion is performed once per DISTINCT (ra_value, dec_value) pair
    and the result is applied to every row carrying that pair. This is not
    an approximation: the transform is a pure function of the input pair.
    The number of distinct pairs and the number of rows are both reported.

THE COMPARISON
    The converted J2000 declination is compared against the sealed B1
    window, -27d 17m to -26d 37m, mechanically and with no tolerance.

    B1 is a declination window. Right ascension enters as a mandatory
    input to the transform, not as a comparison criterion.

REQUIRED FRAMING OF ANY RESULT
    Any B1 outcome here is a result over the CURRENTLY ESTABLISHED PAIRED
    SUBSET. It is not a statement about the source population.

    138 of 918 pages are RA_COLUMN_UNRESOLVED and are absent from this
    input. At least page 014-060 is a full data page carrying 91 stored
    declination rows, one of which reads -27 14, inside the sealed window.
    Unresolved material is therefore demonstrably potentially relevant.

    Consequently: finding B1 rows here establishes EXISTENCE. Finding none
    does NOT establish absence.

    The cause of the RA locator failures is NOT ESTABLISHED. The dense
    channel-column explanation is a hypothesis only and is not recorded as
    a cause.

USAGE
    python tools\\transform_b1_v1.py --rows outputs\\radec_v2\\radec_rows_v3.jsonl
                                     --out outputs\\b1
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

EPOCH_TOOL = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "042_wow", "scripts",
    "wow2_epoch.py")

# Sealed B1 window, from D2_AMENDMENT_v1 (seal d33f79c5...).
B1_NORTH_ARCMIN = -(26 * 60 + 37)
B1_SOUTH_ARCMIN = -(27 * 60 + 17)

ADMISSIBLE = "STRUCTURALLY_ADMISSIBLE"
TOOL_VERSION = "transform_b1_v1"


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_epoch_tool():
    """Import the sealed v1 tool unmodified, from its own project."""
    if not os.path.exists(EPOCH_TOOL):
        print("FAIL: sealed epoch tool not found at %s" % EPOCH_TOOL)
        sys.exit(1)
    import importlib.util
    spec = importlib.util.spec_from_file_location("wow2_epoch", EPOCH_TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_dec(value):
    """'-26 13' -> arcminutes, negative. None if not that exact shape."""
    m = re.fullmatch(r"-(\d{2}) (\d{2})", value or "")
    if not m:
        return None
    return -(int(m.group(1)) * 60 + int(m.group(2)))


def dec_to_astro(value):
    m = re.fullmatch(r"-(\d{2}) (\d{2})", value)
    return "-%sd%sm00s" % (m.group(1), m.group(2))


def ra_to_astro(value):
    m = re.fullmatch(r"(\d{2}) (\d{2}) (\d{2})", value or "")
    if not m:
        return None
    return "%sh%sm%ss" % (m.group(1), m.group(2), m.group(3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    epoch = load_epoch_tool()
    print("sealed epoch tool: %s" % EPOCH_TOOL)
    print("  sha256 %s" % sha256_file(EPOCH_TOOL))
    print("running the sealed tool's own selftest before any conversion")
    epoch.selftest()
    provenance = epoch.provenance()
    print("")

    input_sha256 = sha256_file(args.rows)
    total = 0
    paired = 0
    skipped = defaultdict(int)
    pairs = defaultdict(list)          # (ra_value, dec_value) -> row keys
    rows_index = {}

    with open(args.rows, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            total += 1
            if rec.get("pairing_verdict") != "PAIRED":
                continue
            paired += 1
            d = rec.get("dec") or {}
            r = rec.get("ra") or {}
            if d.get("gate_state") != ADMISSIBLE:
                skipped["dec_not_structurally_admissible"] += 1
                continue
            if r.get("gate_state") != ADMISSIBLE:
                skipped["ra_not_structurally_admissible"] += 1
                continue
            dv, rv = d.get("extractor_value"), r.get("extractor_value")
            if parse_dec(dv) is None:
                skipped["dec_value_unparseable"] += 1
                continue
            if ra_to_astro(rv) is None:
                skipped["ra_value_unparseable"] += 1
                continue
            key = (rec["page"], rec["row_id"])
            rows_index[key] = rec
            pairs[(rv, dv)].append(key)

    print("input rows in file            : %d" % total)
    print("PAIRED rows                   : %d" % paired)
    print("rows eligible for transform   : %d" % sum(len(v) for v in pairs.values()))
    print("distinct (RA, DEC) value pairs: %d" % len(pairs))
    for k in sorted(skipped):
        print("  skipped, %-34s %d" % (k, skipped[k]))
    sys.stdout.flush()

    converted = {}
    errors = {}
    for i, (rv, dv) in enumerate(sorted(pairs)):
        try:
            j = epoch.to_j2000(ra_to_astro(rv), dec_to_astro(dv))
            converted[(rv, dv)] = (j.ra.deg, j.dec.deg)
        except Exception as e:
            errors[(rv, dv)] = "%s: %s" % (type(e).__name__, e)
        if (i + 1) % 200 == 0:
            print("  converted %d/%d distinct pairs" % (i + 1, len(pairs)))
            sys.stdout.flush()

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    rows_out = os.path.join(out_dir, "b1_rows_v1.jsonl")
    summary_out = os.path.join(out_dir, "b1_summary_v1.json")

    inside = outside = errored = 0
    per_run_inside = defaultdict(int)
    with open(rows_out, "w", encoding="utf-8", newline="\n") as f:
        for (rv, dv), keys in sorted(pairs.items()):
            err = errors.get((rv, dv))
            for key in keys:
                rec = rows_index[key]
                base = {
                    "page": rec["page"], "row_id": rec["row_id"],
                    "canonical_y": rec.get("canonical_y"),
                    "run": rec.get("run"), "folder": rec.get("folder"),
                    "source_url": rec.get("source_url"),
                    "local_sha256": rec.get("local_sha256"),
                    "byte_integrity": rec.get("byte_integrity"),
                    "source_authenticity": rec.get("source_authenticity"),
                    "ra_printed_b1950": rv, "dec_printed_b1950": dv,
                    "transform_provenance": provenance,
                    "tool_version": TOOL_VERSION,
                    "subset_scope": "CURRENTLY_ESTABLISHED_PAIRED_SUBSET",
                }
                if err:
                    errored += 1
                    base.update({"transform_state": "TRANSFORM_ERROR",
                                 "transform_error": err,
                                 "b1_state": "NOT_EVALUATED"})
                else:
                    ra_deg, dec_deg = converted[(rv, dv)]
                    arcmin = dec_deg * 60.0
                    is_in = B1_SOUTH_ARCMIN <= arcmin <= B1_NORTH_ARCMIN
                    if is_in:
                        inside += 1
                        per_run_inside[rec.get("run")] += 1
                    else:
                        outside += 1
                    base.update({
                        "transform_state": "TRANSFORMED",
                        "ra_j2000_deg": round(ra_deg, 6),
                        "dec_j2000_deg": round(dec_deg, 6),
                        "dec_j2000_arcmin": round(arcmin, 3),
                        "b1_window_arcmin": [B1_SOUTH_ARCMIN, B1_NORTH_ARCMIN],
                        "b1_state": "INSIDE_SEALED_B1" if is_in else "OUTSIDE_SEALED_B1",
                        "distance_to_nearest_edge_arcmin": round(
                            min(abs(arcmin - B1_NORTH_ARCMIN),
                                abs(arcmin - B1_SOUTH_ARCMIN)), 3),
                    })
                f.write(json.dumps(base) + "\n")

    summary = {
        "tool_version": TOOL_VERSION,
        "transform_provenance": provenance,
        "sealed_epoch_tool": EPOCH_TOOL,
        "sealed_epoch_tool_sha256": sha256_file(EPOCH_TOOL),
        "input_file": os.path.abspath(args.rows),
        "input_file_sha256": input_sha256,
        "input_rows_total": total,
        "paired_rows": paired,
        "rows_transform_eligible": sum(len(v) for v in pairs.values()),
        "distinct_value_pairs": len(pairs),
        "skipped_reasons": dict(skipped),
        "transform_errors_distinct_pairs": len(errors),
        "rows_with_transform_error": errored,
        "rows_inside_sealed_b1": inside,
        "rows_outside_sealed_b1": outside,
        "inside_by_run": dict(per_run_inside),
        "b1_window": "-27d17m to -26d37m, J2000, from D2_AMENDMENT seal d33f79c5",
        "scope_declaration": (
            "Result over the CURRENTLY ESTABLISHED PAIRED SUBSET only. "
            "138 of 918 pages are RA_COLUMN_UNRESOLVED and absent from this "
            "input; at least page 014-060 is a full data page whose stored "
            "declinations include -27 14, inside the sealed window. Finding "
            "rows here establishes existence; finding none does NOT establish "
            "absence."),
        "ra_locator_failure_cause": "NOT_ESTABLISHED",
        "no_pairing_created_or_repaired": True,
        "no_final_manifest_produced": True,
    }
    with open(summary_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

    print("")
    print("rows INSIDE sealed B1  : %d" % inside)
    print("rows OUTSIDE sealed B1 : %d" % outside)
    print("rows with error        : %d" % errored)
    if per_run_inside:
        print("inside by run: %s" % dict(per_run_inside))
    print("")
    print("SCOPE: established paired subset only. 138 pages unresolved and absent.")
    print("Finding rows establishes existence; finding none does not establish absence.")
    print("rows file: %s" % rows_out)
    print("summary:   %s" % summary_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
