#!/usr/bin/env python3
"""run_dec_population_par.py - parallel orchestration of the SAME frozen
declination extractor and validity gate over the B3-eligible population.

PROJECT: 043_wow_discovery (WOW v2 discovery track)

WHAT IS AND IS NOT DIFFERENT FROM run_dec_population.py
    DIFFERENT: pages are processed by a pool of worker processes instead of
    one at a time, and completed pages are written by the parent process.
    NOT DIFFERENT: the analytical path. Each worker imports the frozen
    dec_extractor_v1 and dec_validity_gate_v1 and calls the identical
    functions on the identical bytes. No parameter, threshold, OCR variant,
    consensus rule or gate decision is changed.

    Row output is therefore identical to the serial runner for any given
    page. Only the order in which pages appear in the output file differs,
    and every row carries its own page identity, so order carries no meaning.

WHY PARALLEL IS SAFE HERE
    Each page is independent: nothing in the extractor or the gate depends
    on another page, and no shared state is mutated. Tesseract is invoked as
    a separate process per row in both runners.

INTEGRITY PRECONDITION
    Unchanged: on every start the SHA-256 of both frozen tools is recomputed
    and the run refuses to start on any mismatch.

RESUMABILITY
    Unchanged: a JSON checkpoint of completed page identifiers. Interrupting
    is safe, and the same command resumes. The serial and parallel runners
    share the same checkpoint and output files and may be used
    interchangeably.

USAGE
    python tools\\run_dec_population_par.py --out outputs\\dec_population
    python tools\\run_dec_population_par.py --out outputs\\dec_population --workers 8
    Default worker count is one less than the number of logical CPUs.
"""
import argparse
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dec_extractor_v1 as EX
import dec_validity_gate_v1 as GATE

BASE = "http://naapo.org/~rchilders/N50CH_data/scans/jpg"

EXPECTED_TOOL_SHA256 = {
    "dec_extractor_v1.py": "82bbef167f74b3726472d1fc41f4c8c2f33c5b69110422b3ec3ce1858a0b90f9",
    "dec_validity_gate_v1.py": "99921043119101a5867f4f6e9a7a2e059189708919d73581f78285e0649f47b1",
}

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


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    return sha256_bytes(open(path, "rb").read())


def check_tools():
    here = os.path.dirname(os.path.abspath(__file__))
    problems = []
    for name, expected in EXPECTED_TOOL_SHA256.items():
        got = sha256_file(os.path.join(here, name))
        if got != expected:
            problems.append("%s sha256 %s != expected %s" % (name, got, expected))
        else:
            print("OK    %s sha256 matches the frozen record" % name)
    if problems:
        for p in problems:
            print("FAIL: " + p)
        print("A frozen tool has changed. Production stopped. Nothing written.")
        sys.exit(1)


def fetch_bytes(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))


def load_sha1(folder, cache_dir):
    path = os.path.join(cache_dir, "SHA1SUM.%s" % folder)
    if not os.path.exists(path):
        open(path, "wb").write(fetch_bytes("%s/folder.%s/SHA1SUM" % (BASE, folder)))
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


def work(task):
    """Process one page in a worker. Returns a result dict, never raises."""
    run, folder, stem, published, img_dir = task
    url = "%s/folder.%s/%s.jpg" % (BASE, folder, stem)
    base = {"run": run, "folder": folder, "page": stem, "source_url": url,
            "transport": "PLAIN_HTTP_NO_TLS"}
    local = os.path.join(img_dir, stem + ".jpg")
    try:
        data = fetch_bytes(url)
        open(local, "wb").write(data)
    except Exception as e:
        return dict(base, ok=False, failure="DOWNLOAD", detail=str(e))

    local_sha1 = hashlib.sha1(data).hexdigest()
    local_sha256 = sha256_bytes(data)
    if not published or published != local_sha1:
        try:
            os.remove(local)
        except OSError:
            pass
        return dict(base, ok=False, failure="INTEGRITY",
                    published_sha1=published, local_sha1=local_sha1)

    try:
        rows = GATE.gate_rows(EX.transcribe_page(local))
    except Exception as e:
        try:
            os.remove(local)
        except OSError:
            pass
        return dict(base, ok=False, failure="EXTRACTION",
                    detail="%s: %s" % (type(e).__name__, e))

    try:
        os.remove(local)
    except OSError:
        pass
    return dict(base, ok=True, published_sha1=published, local_sha1=local_sha1,
                local_sha256=local_sha256, rows=rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    args = ap.parse_args()

    check_tools()

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
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
    if args.limit:
        todo = todo[:args.limit]
    print("population %d pages, already done %d, processing %d with %d workers"
          % (len(pages), len(done), len(todo), workers))
    sys.stdout.flush()

    sha1_tables = {}
    tasks = []
    for run, folder, stem in todo:
        if folder not in sha1_tables:
            sha1_tables[folder] = load_sha1(folder, out)
        tasks.append((run, folder, stem, sha1_tables[folder].get(stem + ".jpg"), img))

    processed = 0
    t0 = time.time()
    with mp.Pool(processes=workers) as pool:
        for res in pool.imap_unordered(work, tasks, chunksize=1):
            if not res.get("ok"):
                with open(fail_path, "a") as f:
                    f.write(json.dumps({k: v for k, v in res.items()
                                        if k != "rows"}) + "\n")
                continue
            with open(rows_path, "a") as f:
                for i, r in enumerate(res["rows"]):
                    f.write(json.dumps({
                        "run": res["run"], "folder": res["folder"],
                        "page": res["page"], "row_index": i, "row_y": r["row_y"],
                        "source_url": res["source_url"],
                        "transport": "PLAIN_HTTP_NO_TLS",
                        "source_published_sha1": res["published_sha1"],
                        "source_published_sha1_semantics": "CONSISTENCY_METADATA_ONLY",
                        "local_sha1": res["local_sha1"],
                        "local_sha256": res["local_sha256"],
                        "byte_integrity": "CONSISTENT_WITH_SOURCE_PUBLISHED_CHECKSUM",
                        "source_authenticity": "UNESTABLISHED",
                        "extractor": "dec_extractor_v1",
                        "extractor_sha256": EXPECTED_TOOL_SHA256["dec_extractor_v1.py"],
                        "gate_sha256": EXPECTED_TOOL_SHA256["dec_validity_gate_v1.py"],
                        "raw_reads": r["raw_reads"],
                        "normalised": r["normalised"],
                        "extractor_state": r["state"],
                        "extractor_value": r["value"],
                        "gate_version": r["gate_version"],
                        "gate_state": r["gate_state"],
                        "gate_reason": r["gate_reason"],
                    }) + "\n")
            done.add(res["page"])
            ckpt["done"] = sorted(done)
            json.dump(ckpt, open(ckpt_path, "w"))
            processed += 1
            if processed % 10 == 0:
                el = time.time() - t0
                rate = el / processed
                left = (len(tasks) - processed) * rate
                print("  %d/%d this run, %.1f s/page wall, %d of %d total, "
                      "about %.0f min left"
                      % (processed, len(tasks), rate, len(done), len(pages),
                         left / 60))
                sys.stdout.flush()

    el = time.time() - t0
    print("finished: %d pages in %.0f s (%.2f s/page wall with %d workers)"
          % (processed, el, el / processed if processed else 0, workers))
    print("total complete: %d of %d" % (len(done), len(pages)))
    print("rows file:      %s" % rows_path)
    print("checkpoint:     %s" % ckpt_path)
    print("failures file:  %s" % fail_path)


if __name__ == "__main__":
    mp.freeze_support()
    main()
