#!/usr/bin/env python3
"""mk_b1_review_order_v1.py - deterministic operational review ordering over
the frozen 978-row statistical sample.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

WHY THIS EXISTS
    The frozen sample file is written grouped by stratum, so reading it in
    file order would make the first batch almost entirely R-09. That does
    not change the final result after all 978 rows, but it would make any
    interim figure unrepresentative of the population.

    This tool produces an ORDERING ONLY. The statistical sample is not
    touched: no row is added, removed or reweighted, and every inclusion
    probability stands as frozen.

NO SOURCE IMAGE IS OPENED BY THIS SCRIPT.

METHOD
    Within each run the rows are ordered by
        SHA256("B1_REVIEW_ORDER_V1|" + sample_sha256 + "|" + page + "|" + row_id)
    ascending. Each run's rows are then split across the batches by largest
    remainder, so every batch carries approximately the frozen n_h
    proportions. The batch a row lands in is therefore fixed before any
    image is seen and cannot be influenced by what the images show.

PROOF OBLIGATIONS, all checked and recorded
    every sample row occurs exactly once across all batches
    no row outside the frozen sample enters
    no row is omitted
    the ordered set equals the frozen sample set exactly

USAGE
    python tools\\mk_b1_review_order_v1.py
        --sample research\\v2_b1\\B1_POPULATION_SAMPLE_v1.jsonl
        --batch-size 100
        --out research\\v2_b1
"""
import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter, defaultdict

PREFIX = "B1_REVIEW_ORDER_V1"
ORDER_VERSION = "B1_POPULATION_REVIEW_ORDER_v1"


def largest_remainder(total, parts):
    """Split total into `parts` integers summing exactly to total."""
    base = [total // parts] * parts
    for i in range(total - sum(base)):
        base[i] += 1
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--batch-size", type=int, default=100)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    sample_path = os.path.abspath(args.sample)
    sample_sha = hashlib.sha256(open(sample_path, "rb").read()).hexdigest()

    rows = []
    with open(sample_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    total = len(rows)
    n_batches = int(math.ceil(total / args.batch_size))

    by_run = defaultdict(list)
    for r in rows:
        by_run[r["stratum"]].append(r)

    # deterministic within-run order
    def score(r):
        return hashlib.sha256(
            ("%s|%s|%s|%d" % (PREFIX, sample_sha, r["page"], r["row_id"]))
            .encode("utf-8")).hexdigest()

    batches = [[] for _ in range(n_batches)]
    per_run_per_batch = {}
    for run in sorted(by_run):
        ordered = sorted(by_run[run], key=score)
        split = largest_remainder(len(ordered), n_batches)
        per_run_per_batch[run] = split
        pos = 0
        for b, take in enumerate(split):
            for r in ordered[pos:pos + take]:
                r2 = dict(r)
                r2["review_batch"] = b + 1
                r2["review_order_score"] = score(r)
                r2["order_version"] = ORDER_VERSION
                batches[b].append(r2)
            pos += take

    # within a batch, order by run then score, purely for a readable file
    out_rows = []
    for b, batch in enumerate(batches):
        for r in sorted(batch, key=lambda x: (x["stratum"], x["review_order_score"])):
            r["review_index"] = len(out_rows) + 1
            out_rows.append(r)

    # proofs
    sample_keys = set(r["key"] for r in rows)
    order_keys = [r["key"] for r in out_rows]
    order_key_set = set(order_keys)
    dupes = len(order_keys) - len(order_key_set)
    missing = sorted(sample_keys - order_key_set)
    extra = sorted(order_key_set - sample_keys)

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    order_path = os.path.join(out_dir, "B1_POPULATION_REVIEW_ORDER_v1.jsonl")
    with open(order_path, "w", encoding="utf-8", newline="\n") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")
    order_sha = hashlib.sha256(open(order_path, "rb").read()).hexdigest()

    batch_table = []
    for b in range(n_batches):
        rows_b = [r for r in out_rows if r["review_batch"] == b + 1]
        batch_table.append({
            "batch": b + 1,
            "rows": len(rows_b),
            "by_run": dict(Counter(r["stratum"] for r in rows_b)),
        })

    prereg = {
        "artifact": "B1_POPULATION_REVIEW_ORDER_PREREGISTRATION_v1",
        "artifact_kind": "operational_pre_registration",
        "project": "043_wow_discovery",
        "record_version": 1,
        "created_utc": "2026-09-24",
        "pre_seal_status": "OPERATIONAL-WORK-RECORD-NOT-FOR-SEALING",
        "status_semantics": "No field named status. Written before any sampled source image is opened.",
        "no_source_image_opened_by_this_step": "YES",
        "what_this_is": "An operational review ORDER over the frozen statistical sample. It changes no membership, no inclusion probability and no weight.",
        "why": "The frozen sample file is written grouped by stratum. Reading it in file order would make early batches almost entirely one run, so any interim figure would not represent the population. This ordering makes every batch carry approximately the frozen stratum proportions.",
        "input": {
            "sample_file": "research/v2_b1/B1_POPULATION_SAMPLE_v1.jsonl",
            "sample_sha256": sample_sha,
            "sample_rows": total,
        },
        "ordering_rule": {
            "score": "SHA256(\"%s|\" + sample_sha256 + \"|\" + source_page + \"|\" + row_id)" % PREFIX,
            "within": "each run, ascending",
            "batching": "each run's ordered rows split across the batches by largest remainder, so batch composition approximates the frozen n_h proportions",
            "determinism": "no RNG, no image information, no cadence, no value dependence",
        },
        "batch_size_target": args.batch_size,
        "batches": n_batches,
        "batch_table": batch_table,
        "per_run_per_batch": per_run_per_batch,
        "proofs": {
            "sample_rows": total,
            "ordered_rows": len(out_rows),
            "distinct_ordered_keys": len(order_key_set),
            "duplicates": dupes,
            "missing_from_order": len(missing),
            "extra_in_order": len(extra),
            "set_equality_with_frozen_sample": (dupes == 0 and not missing and not extra),
        },
        "review_states": [
            "SOURCE_CONFIRMED",
            "TRANSCRIPTION_ERROR_B1_CHANGING",
            "TRANSCRIPTION_ERROR_NON_B1_CHANGING",
            "NOT_ESTABLISHED"
        ],
        "per_field_rule": "Right ascension and declination are judged independently. Where a stored field is wrong, the corrected value is established from the source image and the sealed transform is rerun. A correction is never inferred from cadence.",
        "interim_reporting_rule": "An interim figure after any batch is a partial result over the frozen sample and must be reported as such, with the batches completed and the rows reviewed stated explicitly.",
        "order_file": "research/v2_b1/B1_POPULATION_REVIEW_ORDER_v1.jsonl",
        "order_sha256": order_sha,
    }
    prereg_path = os.path.join(out_dir, "B1_POPULATION_REVIEW_ORDER_PREREGISTRATION_v1.json")
    with open(prereg_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(prereg, f, indent=2)
        f.write("\n")

    print("input sample rows        : %d" % total)
    print("input sample sha256      : %s" % sample_sha)
    print("batches                  : %d" % n_batches)
    print("ordered rows             : %d" % len(out_rows))
    print("distinct keys            : %d" % len(order_key_set))
    print("duplicates               : %d" % dupes)
    print("missing / extra          : %d / %d" % (len(missing), len(extra)))
    print("set equality with sample : %s" % (dupes == 0 and not missing and not extra))
    print("order sha256             : %s" % order_sha)
    print("")
    print("%-7s %6s  %s" % ("batch", "rows", "by run"))
    for b in batch_table:
        print("%-7d %6d  %s" % (b["batch"], b["rows"],
              " ".join("%s:%d" % (k, v) for k, v in sorted(b["by_run"].items()))))
    print("")
    print("written: %s" % order_path)
    print("written: %s" % prereg_path)
    print("NO SOURCE IMAGE OPENED. Freeze both before batch 1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
