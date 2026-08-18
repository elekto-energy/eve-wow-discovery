#!/usr/bin/env python3
"""run_dec_population.py - checkpointed, resumable production run of the
frozen declination extractor over the B3-eligible population.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

WHAT THIS DOES
    Downloads each page of the B3-eligible runs, verifies its bytes against
    the folder SHA1SUM published by the origin, runs the frozen extractor
    dec_extractor_v1, applies the frozen structural validity gate
    dec_validity_gate_v1, and appends per-row records to a JSONL file.

WHAT THIS NEVER DOES
    It never reads channel, intensity, frequency, galactic or object fields.
    The extractor's column window stops before the frequency column, so
    signal-adjacent content is not exposed during spatial screening.
    It never repairs an OCR value.
    It never modifies the frozen extractor or the frozen gate.

INTEGRITY PRECONDITION
    On every start the script recomputes the SHA-256 of both frozen tools and
    refuses to run if either differs from the value recorded here. A tool that
    has drifted must not silently produce production data.

RESUMABILITY
    Progress is a JSON checkpoint listing completed page identifiers. A rerun
    skips completed pages. Interrupting the run at any point is safe.

USAGE
    python tools\\run_dec_population.py --out outputs\\dec_population
    python tools\\run_dec_population.py --out outputs\\dec_population --limit 200
    Rerun the same command to resume.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dec_extractor_v1 as EX
import dec_validity_gate_v1 as GATE

BASE = "http://naapo.org/~rchilders/N50CH_data/scans/jpg"

EXPECTED_TOOL_SHA256 = {
    "dec_extractor_v1.py": "82bbef167f74b3726472d1fc41f4c8c2f33c5b69110422b3ec3ce1858a0b90f9",
    "dec_validity_gate_v1.py": "PENDING_OWNER_COMPUTATION",
}

# The fifteen B3-eligible runs, from PHASE_A_RUN_INVENTORY_v1.json.
# run id -> (folder, first data page, last data page)
RUNS = [
    ("R-03", "012", 456, 552), ("R-04", "013", 2, 71),
    ("R-05", "013", 73, 83),   ("R-06", "013", 85, 87),
    ("R-07", "013", 89, 142),  ("R-08", "013", 144, 236),
    ("R-09", "013", 238, 411), ("R-10", "013", 413, 455),
    ("R-11", "013", 457, 467), ("R-12", "014", 2, 57),
    ("R-13", "014", 59, 146),  ("R-14", "014", 149, 219),
    ("R-15", "014", 221, 296), ("R-16", "014", 298, 365),
    ("R-17", "014", 367, 369),
]


def sha256_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def check_tools():
    here = os.path.dirname(os.path.abspath(__file__))
    problems = []
    for name, expected in EXPECTED_TOOL_SHA256.items():
        got = sha256_file(os.path.join(here, name))
        if expected == "PENDING_OWNER_COMPUTATION":
            print("NOTE  %s sha256 %s  (expected value not yet recorded)" % (name, got))
            continue
        if got != expected:
            problems.append("%s sha256 %s != expected %s" % (name, got, expected))
        else:
            print("OK    %s sha256 matches the frozen record" % name)
    if problems:
        for p in problems:
            print("FAIL: " + p)
        print("A frozen tool has changed. Production stopped. Nothing written.")
        sys.exit(1)


def fetch(url, dest, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                data = r.read()
            open(dest, "wb").write(data)
            return len(data)
        except Exception as e:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def load_sha1(folder, cache_dir):
    path = os.path.join(cache_dir, "SHA1SUM.%s" % folder)
    if not os.path.exists(path):
        fetch("%s/folder.%s/SHA1SUM" % (BASE, folder), path)
    table = {}
    for line in open(path):
        parts = line.split()
        if len(parts) == 2:
            table[parts[1]] = parts[0]
    return table


def page_list():
    pages = []
    for run, folder, a, b in RUNS:
        for n in range(a, b + 1):
            pages.append((run, folder, "%s-%03d" % (folder, n)))
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--limit", type=int, default=0, help="stop after N pages this run")
    ap.add_argument("--keep-images", action="store_true",
                    help="keep downloaded page images instead of deleting them")
    args = ap.parse_args()

    check_tools()

    out = os.path.abspath(args.out)
    img = os.path.join(out, "pages")
    os.makedirs(img, exist_ok=True)
    rows_path = os.path.join(out, "dec_rows.jsonl")
    ckpt_path = os.path.join(out, "checkpoint.json")
    fail_path = os.path.join(out, "failures.jsonl")

    ckpt = json.load(open(ckpt_path)) if os.path.exists(ckpt_path) else {"done": []}
    done = set(ckpt["done"])

    pages = page_list()
    todo = [p for p in pages if p[2] not in done]
    print("population %d pages, already done %d, remaining %d"
          % (len(pages), len(done), len(todo)))

    sha1_tables = {}
    processed = 0
    t0 = time.time()
    for run, folder, stem in todo:
        if args.limit and processed >= args.limit:
            break
        if folder not in sha1_tables:
            sha1_tables[folder] = load_sha1(folder, out)
        url = "%s/folder.%s/%s.jpg" % (BASE, folder, stem)
        local = os.path.join(img, stem + ".jpg")
        rec_common = {"run": run, "folder": folder, "page": stem, "source_url": url,
                      "transport": "PLAIN_HTTP_NO_TLS"}
        try:
            nbytes = fetch(url, local)
        except Exception as e:
            with open(fail_path, "a") as f:
                f.write(json.dumps(dict(rec_common, failure="DOWNLOAD",
                                        detail=str(e))) + "\n")
            continue

        published = sha1_tables[folder].get(stem + ".jpg")
        local_sha1 = hashlib.sha1(open(local, "rb").read()).hexdigest()
        local_sha256 = sha256_file(local)
        integrity = ("CONSISTENT_WITH_SOURCE_PUBLISHED_CHECKSUM"
                     if published and published == local_sha1 else "MISMATCH_OR_ABSENT")
        if integrity != "CONSISTENT_WITH_SOURCE_PUBLISHED_CHECKSUM":
            with open(fail_path, "a") as f:
                f.write(json.dumps(dict(rec_common, failure="INTEGRITY",
                                        published_sha1=published,
                                        local_sha1=local_sha1)) + "\n")
            if not args.keep_images:
                os.remove(local)
            continue

        try:
            rows = EX.transcribe_page(local)
            rows = GATE.gate_rows(rows)
        except Exception as e:
            with open(fail_path, "a") as f:
                f.write(json.dumps(dict(rec_common, failure="EXTRACTION",
                                        detail="%s: %s" % (type(e).__name__, e))) + "\n")
            if not args.keep_images:
                os.remove(local)
            continue

        with open(rows_path, "a") as f:
            for i, r in enumerate(rows):
                f.write(json.dumps({
                    "run": run, "folder": folder, "page": stem,
                    "row_index": i, "row_y": r["row_y"],
                    "source_url": url,
                    "transport": "PLAIN_HTTP_NO_TLS",
                    "source_published_sha1": published,
                    "source_published_sha1_semantics": "CONSISTENCY_METADATA_ONLY",
                    "local_sha1": local_sha1,
                    "local_sha256": local_sha256,
                    "byte_integrity": integrity,
                    "source_authenticity": "UNESTABLISHED",
                    "extractor": "dec_extractor_v1",
                    "extractor_sha256": EXPECTED_TOOL_SHA256["dec_extractor_v1.py"],
                    "raw_reads": r["raw_reads"],
                    "normalised": r["normalised"],
                    "extractor_state": r["state"],
                    "extractor_value": r["value"],
                    "gate_version": r["gate_version"],
                    "gate_state": r["gate_state"],
                    "gate_reason": r["gate_reason"],
                }) + "\n")

        done.add(stem)
        ckpt["done"] = sorted(done)
        json.dump(ckpt, open(ckpt_path, "w"))
        if not args.keep_images:
            os.remove(local)
        processed += 1
        if processed % 10 == 0:
            el = time.time() - t0
            print("  %d pages this run, %.1f s/page, %d of %d total"
                  % (processed, el / processed, len(done), len(pages)))

    el = time.time() - t0
    print("finished this invocation: %d pages in %.0f s (%.1f s/page)"
          % (processed, el, el / processed if processed else 0))
    print("total complete: %d of %d" % (len(done), len(pages)))
    print("rows file:      %s" % rows_path)
    print("checkpoint:     %s" % ckpt_path)
    print("failures file:  %s" % fail_path)


if __name__ == "__main__":
    main()
