#!/usr/bin/env python3
"""mk_b1_population_sample_v1.py - materialise the sampling frame, compute the
sample size, allocate by run, and select the sample deterministically.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

PURPOSE
    Estimate transcription reliability in the previously unreviewed,
    established-paired, currently-inside-B1 population.

    This is NOT an audit of the 138 RA_COLUMN_UNRESOLVED pages.
    This is NOT an estimate for the full historical source population.
    It applies only to the sampling frame materialised here.

NO SOURCE IMAGE IS OPENED BY THIS SCRIPT.

EXCLUSIONS
    Every row already source-reviewed is removed from the frame:
    the 2 class-1 rows and the 24 rows of the preregistered class 2 and 3
    union. Those 26 were deliberately risk-selected and must never
    contribute to a population estimate. They may later be shown only as a
    separate risk-selected comparison group.

SAMPLE SIZE
    n = N z^2 p(1-p) / ( e^2 (N-1) + z^2 p(1-p) )
    with z = 1.96, p = 0.5 conservative, e = 0.03, and the exact
    materialised N. Finite population correction is inherent in the form.

STRATIFICATION
    Primary strata: RUN. Run is observable before any image is inspected,
    is historically meaningful, and cannot be affected by later reading.
    No cross-product strata are created.

    Pre-image variables are preserved for preregistered subgroup analysis
    but never used to change a verdict. Frequency bands are fixed here
    BEFORE sampling; a band that turns out empty is retained as an empty
    predefined band rather than redefined.

ALLOCATION
    Proportional by run, n_h approximately n * N_h / N, resolved with
    largest-remainder so that the allocations sum exactly to n. Inclusion
    probability and weight are recorded per stratum. No post-inspection
    change to any n_h.

SELECTION
    Deterministic, not an interactive RNG. For each row the immutable key
    is source_page|row_id and the selection score is
        SHA256(seed || "|" || source_page || "|" || row_id)
    Within each run the rows are sorted ascending by score and the first
    n_h taken. This reproduces identically under any Python version.

    The seed must be supplied as the full commit identity of the frozen
    pre-sampling repository state. It is never generated here.

USAGE
    python tools\\mk_b1_population_sample_v1.py
        --rows outputs\\b1\\b1_rows_v1.jsonl
        --reviewed research\\v2_b1\\B1_REVIEW_PREREGISTRATION_v1.json
        --seed <full commit sha>
        --out research\\v2_b1
"""
import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict

Z = 1.96
P = 0.5
E = 0.03

CLASS1_ROWS = [("013-063", 27), ("013-193", 85)]

DEC_FREQ_BANDS = [("10-49", 10, 49), ("50-199", 50, 199), ("200+", 200, 10 ** 9)]
PAGE_HIT_BANDS = [("4-9", 4, 9), ("10-49", 10, 49), ("50+", 50, 10 ** 9)]


def band(value, bands):
    for name, lo, hi in bands:
        if lo <= value <= hi:
            return name
    return "BELOW_LOWEST_BAND"


def sample_size(N):
    num = N * Z * Z * P * (1 - P)
    den = E * E * (N - 1) + Z * Z * P * (1 - P)
    return int(math.ceil(num / den))


def largest_remainder(n, sizes):
    """Allocate n proportionally to sizes so the parts sum exactly to n."""
    total = sum(sizes.values())
    exact = {k: n * v / total for k, v in sizes.items()}
    base = {k: int(math.floor(v)) for k, v in exact.items()}
    remaining = n - sum(base.values())
    order = sorted(exact, key=lambda k: (-(exact[k] - base[k]), k))
    for k in order[:remaining]:
        base[k] += 1
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True)
    ap.add_argument("--reviewed", required=True)
    ap.add_argument("--seed", required=True,
                    help="full commit sha of the frozen pre-sampling state")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if len(args.seed) < 40:
        print("FAIL: seed must be the full 40-character commit identity.")
        return 1

    reviewed = set("%s|%d" % (p, i) for p, i in CLASS1_ROWS)
    prereg = json.load(open(args.reviewed, "r", encoding="utf-8"))
    for r in prereg.get("rows_to_review", []):
        reviewed.add("%s|%d" % (r["page"], r["row_id"]))

    inside = []
    with open(args.rows, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("b1_state") == "INSIDE_SEALED_B1":
                inside.append(rec)

    dec_counts = Counter(r["dec_printed_b1950"] for r in inside)
    page_counts = Counter(r["page"] for r in inside)

    frame = []
    seen = set()
    duplicates = []
    excluded = 0
    for r in inside:
        key = "%s|%d" % (r["page"], r["row_id"])
        if key in reviewed:
            excluded += 1
            continue
        if key in seen:
            duplicates.append(key)
            continue
        seen.add(key)
        frame.append({
            "key": key, "page": r["page"], "row_id": r["row_id"],
            "run": r["run"],
            "stored_ra_b1950": r["ra_printed_b1950"],
            "stored_dec_b1950": r["dec_printed_b1950"],
            "dec_value_occurrences_in_b1": dec_counts[r["dec_printed_b1950"]],
            "page_b1_hits": page_counts[r["page"]],
            "dec_freq_band": band(dec_counts[r["dec_printed_b1950"]], DEC_FREQ_BANDS),
            "page_hit_band": band(page_counts[r["page"]], PAGE_HIT_BANDS),
            "distance_to_nearest_edge_arcmin": r.get("distance_to_nearest_edge_arcmin"),
            "dec_j2000_arcmin": r.get("dec_j2000_arcmin"),
            "local_sha256": r.get("local_sha256"),
            "source_url": r.get("source_url"),
        })

    N = len(frame)
    n = sample_size(N)
    by_run = defaultdict(list)
    for row in frame:
        by_run[row["run"]].append(row)
    sizes = {k: len(v) for k, v in by_run.items()}
    alloc = largest_remainder(n, sizes)

    strata = []
    sample = []
    for run in sorted(by_run):
        rows = by_run[run]
        n_h = alloc[run]
        scored = sorted(
            rows,
            key=lambda r: hashlib.sha256(
                ("%s|%s|%d" % (args.seed, r["page"], r["row_id"])).encode("utf-8")
            ).hexdigest())
        chosen = scored[:n_h]
        for r in chosen:
            r2 = dict(r)
            r2["stratum"] = run
            r2["selection_score"] = hashlib.sha256(
                ("%s|%s|%d" % (args.seed, r["page"], r["row_id"])).encode("utf-8")
            ).hexdigest()
            sample.append(r2)
        strata.append({
            "run": run, "N_h": len(rows), "n_h": n_h,
            "inclusion_probability": round(n_h / len(rows), 6) if rows else None,
            "weight": round(len(rows) / n_h, 6) if n_h else None,
        })

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    sample_path = os.path.join(out_dir, "B1_POPULATION_SAMPLE_v1.jsonl")
    with open(sample_path, "w", encoding="utf-8", newline="\n") as f:
        for r in sorted(sample, key=lambda x: (x["stratum"], x["key"])):
            f.write(json.dumps(r) + "\n")
    sample_sha = hashlib.sha256(open(sample_path, "rb").read()).hexdigest()

    prereg_out = {
        "artifact": "B1_POPULATION_SAMPLE_PREREGISTRATION_v1",
        "artifact_kind": "operational_pre_registration",
        "project": "043_wow_discovery",
        "record_version": 1,
        "created_utc": "2026-09-24",
        "pre_seal_status": "OPERATIONAL-WORK-RECORD-NOT-FOR-SEALING",
        "status_semantics": "No field named status. Written before any sampled source image is opened.",
        "no_source_image_opened_by_this_step": "YES",
        "sampling_frame": {
            "started_from": "rows classified INSIDE_SEALED_B1 in the established paired subset",
            "inside_rows_total": len(inside),
            "excluded_already_reviewed": excluded,
            "excluded_detail": "2 class-1 rows and 24 rows of the preregistered class 2 and 3 union; all 26 were deliberately risk-selected and may never contribute to a population estimate",
            "duplicate_keys_found": len(duplicates),
            "N": N,
            "distinct_keys": len(seen),
            "counts_by_run": sizes,
            "distinct_source_pages": len(set(r["page"] for r in frame)),
            "dec_frequency_bands_fixed_before_sampling": [b[0] for b in DEC_FREQ_BANDS],
            "page_hit_bands_fixed_before_sampling": [b[0] for b in PAGE_HIT_BANDS],
            "dec_freq_band_counts": dict(Counter(r["dec_freq_band"] for r in frame)),
            "page_hit_band_counts": dict(Counter(r["page_hit_band"] for r in frame)),
        },
        "sample_size": {
            "target": "95 percent confidence, absolute margin of error at most 0.03",
            "z": Z, "p_conservative": P, "e": E,
            "formula": "n = N z^2 p(1-p) / ( e^2 (N-1) + z^2 p(1-p) )",
            "n": n,
        },
        "stratification": {
            "primary_stratum": "RUN",
            "why": "observable before any image is inspected, historically meaningful, and unaffected by later reading",
            "no_cross_product_strata": True,
            "allocation": "proportional, resolved by largest remainder so the parts sum exactly to n",
            "strata": strata,
            "sum_n_h": sum(s["n_h"] for s in strata),
        },
        "selection": {
            "method": "deterministic, no interactive RNG",
            "seed": args.seed,
            "seed_origin": "full commit identity of the frozen pre-sampling repository state, supplied by the owner",
            "score": "SHA256(seed | source_page | row_id), ascending, first n_h within each run",
            "reproducible_without_python_rng": True,
        },
        "row_level_review_states": [
            "SOURCE_CONFIRMED",
            "TRANSCRIPTION_ERROR_B1_CHANGING",
            "TRANSCRIPTION_ERROR_NON_B1_CHANGING",
            "NOT_ESTABLISHED"
        ],
        "per_field_states_preserved_separately": "RA and DEC each recorded as confirmed, error or not established. A correction is never inferred from cadence where the source image does not establish the value.",
        "primary_measures": [
            "P(any transcription error)",
            "P(B1-changing transcription error)",
            "P(coordinate error AND B1 membership remains correct)"
        ],
        "additional_measure": {
            "measure": "P(coordinate error | B1 membership remains correct)",
            "caveat": "Its precision depends on the observed denominator and is not guaranteed by the sample size above."
        },
        "estimation": {
            "per_stratum": "observed proportions with Wilson 95 percent intervals",
            "overall": "p_hat = sum_h (N_h/N) p_h, with stratified design-based finite-population variance for the primary interval",
            "explicit_prohibition": "An ordinary Wilson interval must NOT be applied to the weighted stratified total and labelled design-correct."
        },
        "preregistered_secondary_analysis": "Outcomes reported by DEC-frequency band, page-hit-count band and run, without changing the primary estimator. The 26 previously reviewed rows remain external and may appear only as a separate risk-selected comparison group.",
        "scope_boundary": {
            "applies_to": "established-paired, currently classified inside B1, previously unreviewed rows",
            "does_not_establish": [
                "error rate on the 138 RA_COLUMN_UNRESOLVED pages",
                "completeness of B1",
                "error rate for the complete Ohio SETI archive",
                "error rate in the PHL/Arecibo private dataset",
                "correctness or incorrectness of Arecibo Wow! II"
            ]
        },
        "sample_file": "research/v2_b1/B1_POPULATION_SAMPLE_v1.jsonl",
        "sample_sha256": sample_sha,
        "sample_rows": len(sample),
        "proof_no_reviewed_row_entered": {
            "reviewed_keys": len(reviewed),
            "intersection_with_sample": len(set(r["key"] for r in sample) & reviewed),
        },
        "proof_no_duplicate_keys": {
            "duplicates_in_frame": len(duplicates),
            "sample_keys": len(sample),
            "distinct_sample_keys": len(set(r["key"] for r in sample)),
        },
    }
    prereg_path = os.path.join(out_dir, "B1_POPULATION_SAMPLE_PREREGISTRATION_v1.json")
    with open(prereg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(prereg_out, f, indent=2)
        f.write("\n")

    print("inside rows                 : %d" % len(inside))
    print("excluded already reviewed   : %d" % excluded)
    print("duplicate keys in frame     : %d" % len(duplicates))
    print("ELIGIBLE POPULATION N       : %d" % N)
    print("computed sample size n      : %d" % n)
    print("sum of allocations          : %d" % sum(s["n_h"] for s in strata))
    print("sample rows written         : %d" % len(sample))
    print("distinct sample keys        : %d" % len(set(r["key"] for r in sample)))
    print("reviewed rows in sample     : %d" % len(set(r["key"] for r in sample) & reviewed))
    print("sample sha256               : %s" % sample_sha)
    print("")
    print("%-6s %8s %6s %10s %10s" % ("run", "N_h", "n_h", "pi_h", "weight"))
    for s in strata:
        print("%-6s %8d %6d %10.5f %10.3f"
              % (s["run"], s["N_h"], s["n_h"], s["inclusion_probability"], s["weight"]))
    print("")
    print("written: %s" % sample_path)
    print("written: %s" % prereg_path)
    print("NO SOURCE IMAGE OPENED. Freeze both files before any review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
