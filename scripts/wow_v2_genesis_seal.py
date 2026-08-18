#!/usr/bin/env python3
# wow_v2_genesis_seal.py - genesis and discovery-protocol seal for WOW v2.
#
# THIS IS A NEW PROJECT'S FIRST LAYER, NOT A CONTINUATION OF WOW v1.
# It chains to the frozen WOW v1 closure identity and can never write to,
# re-seal, or otherwise touch project 042_wow.
#
# ORDERING ENFORCEMENT:
# The tool refuses to seal unless it can re-derive the WOW v1 closure pin
# identity from the v1 pin record on disk and that identity matches the
# genesis field of WOW_V2_GENESIS_v1.json. That makes the sequence
#     v1 closed and pinned -> v2 genesis bound -> discovery questions frozen
#         -> only then archive data opened
# a machine-checked fact rather than an intention.
#
# HASH PROVENANCE RULE (controller order 2026-08-18): no hash is accepted
# from configuration or memory when it can be re-derived from the artifact.
# The expected closure identity below is a fail-hard cross-check, not the
# source of truth; the value used is the one re-derived from disk.
#
# STATUS SEMANTICS: sealed records carry pre_seal_status and no field named
# status. Current lifecycle state lives ONLY here, in seal_payload.decision.
#
# NO NEW MACHINERY: canonicalization, value-domain validation, determinism
# check, fail-hard and write-once behaviour are the WOW v1 primitives,
# unchanged. No new confidence or sealing semantics are introduced.
#
# Default mode: verify only (writes nothing). --seal writes
# research/v2_genesis/WOW_V2_GENESIS_SEAL.json once and refuses to overwrite.
# Python 3 stdlib only.

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

EXPECTED_V1_CLOSURE_PIN = "679e3e48d7ac2ce8653d8e385248388883284828549151e99f00ba1df823c3ae"

# WOW v1 lives in a separate project and is READ ONLY from here.
V1_PIN_RECORD_DEFAULT = os.path.join(
    "..", "042_wow", "research", "wow1_final", "WOW1_CLOSURE_PIN.json")

DOCUMENTS = [
    "research/v2_genesis/WOW_V2_GENESIS_v1.json",
    "research/v2_genesis/DISCOVERY_PROTOCOL_v1.json",
]
SEAL_PATH = "research/v2_genesis/WOW_V2_GENESIS_SEAL.json"


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def validate_values(node, path="$"):
    if isinstance(node, dict):
        for k, v in node.items():
            if not isinstance(k, str):
                raise ValueError("non-string key at %s" % path)
            if k == "status":
                raise ValueError("forbidden field name status at %s" % path)
            validate_values(v, path + "." + k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            validate_values(v, "%s[%d]" % (path, i))
    elif isinstance(node, bool) or node is None or isinstance(node, float):
        raise ValueError("forbidden scalar type %s at %s" % (type(node).__name__, path))
    elif isinstance(node, (str, int)):
        return
    else:
        raise ValueError("unsupported type %s at %s" % (type(node).__name__, path))


def determinism_check(raw_bytes, label):
    obj1 = json.loads(raw_bytes.decode("utf-8"))
    c1 = canonical_bytes(obj1)
    c2 = canonical_bytes(json.loads(c1.decode("utf-8")))
    if c1 != c2 or sha256_bytes(c1) != sha256_bytes(c2):
        raise ValueError("nondeterministic canonicalization for %s" % label)
    return obj1, c1


def fail(msg):
    print("FAIL: %s" % msg)
    print("Nothing written.")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="WOW v2 genesis and protocol seal")
    ap.add_argument("--seal", action="store_true", help="write the seal record")
    ap.add_argument("--root", default=None, help="project root")
    ap.add_argument("--v1-pin", default=None,
                    help="path to the WOW v1 closure pin record (read only)")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(args.root) if args.root else os.path.dirname(here)
    print("WOW v2 genesis seal tool. Root: %s" % root)

    # GATE 1: re-derive the WOW v1 closure identity from the v1 record on disk.
    v1_pin_path = os.path.abspath(
        args.v1_pin if args.v1_pin
        else os.path.join(root, V1_PIN_RECORD_DEFAULT))
    if not os.path.exists(v1_pin_path):
        fail("WOW v1 closure pin record not found at %s. WOW v2 cannot be "
             "sealed without re-deriving the parent identity from the frozen "
             "v1 release." % v1_pin_path)
    with open(v1_pin_path, "rb") as f:
        v1 = json.loads(f.read().decode("utf-8"))
    v1_payload = v1.get("pin_payload", {})
    v1_hash = sha256_bytes(canonical_bytes(v1_payload))
    if v1_hash != v1.get("wow1_closure_pin_hash"):
        fail("re-derived WOW v1 closure identity %s does not match the value "
             "stored in the v1 record" % v1_hash)
    if v1_hash != EXPECTED_V1_CLOSURE_PIN:
        fail("re-derived WOW v1 closure identity %s != expected %s - a hash "
             "mismatch on the parent identity is a finding to investigate, "
             "never to accept" % (v1_hash, EXPECTED_V1_CLOSURE_PIN))
    if v1_payload.get("decision") != "WOW_V1_CLOSED_COMPLETE_AS_METHOD_STUDY":
        fail("WOW v1 is not in the closed state; v2 may only chain to a "
             "closed v1")
    print("RE-DERIVE WOW v1 CLOSURE  PASS")
    print("  %s" % v1_hash)

    entries = []
    genesis_field = None
    for rel in DOCUMENTS:
        path = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.exists(path):
            fail("required v2 document missing: %s" % rel)
        with open(path, "rb") as f:
            raw = f.read()
        obj, canon = determinism_check(raw, rel)
        validate_values(obj, rel)
        entries.append({
            "name": os.path.basename(rel),
            "path": rel,
            "raw_sha256": sha256_bytes(raw),
            "canonical_sha256": sha256_bytes(canon),
        })
        if obj.get("artifact") == "WOW_V2_GENESIS_v1":
            genesis_field = obj.get("genesis")
        if obj.get("artifact") == "DISCOVERY_PROTOCOL_v1":
            bound = obj.get("bound_to", {}).get("wow_v2_genesis")
            if bound != v1_hash:
                fail("DISCOVERY_PROTOCOL_v1 is bound to %s, which is not the "
                     "re-derived v1 closure identity" % bound)
            ids = [q.get("id") for q in obj.get("frozen_questions", [])]
            if ids != ["D1", "D2", "D3"]:
                fail("frozen_questions must be exactly D1, D2, D3; found %s" % ids)
            outcomes = set(obj.get("predeclared_outcomes", {}).keys())
            required = {"NOVEL_CANDIDATE_FOUND", "NO_NOVEL_RESULT_FOUND",
                        "INSUFFICIENT_DATA"}
            if outcomes != required:
                fail("predeclared_outcomes must be exactly %s; found %s"
                     % (sorted(required), sorted(outcomes)))
        print("%s" % rel)
        print("  raw       %s" % entries[-1]["raw_sha256"])
        print("  canonical %s" % entries[-1]["canonical_sha256"])

    # GATE 2: the genesis record must chain to the re-derived identity.
    if genesis_field != v1_hash:
        fail("WOW_V2_GENESIS_v1 genesis field %s does not match the "
             "re-derived WOW v1 closure identity %s" % (genesis_field, v1_hash))
    print("CHAIN TO v1 CLOSURE       PASS")
    print("ORDERING                  OK (questions frozen before any archive "
          "data is opened)")
    print("")

    entries.sort(key=lambda e: e["name"])
    seal_payload_out = {
        "schema": "wow-v2-genesis-seal",
        "schema_version": "1",
        "decision": "WOW_V2_DISCOVERY_PROTOCOL_SEALED",
        "decision_semantics": "The three discovery questions D1, D2 and D3 and "
                              "the three predeclared outcomes are frozen as of "
                              "this seal. No N50CH archive data had been opened "
                              "at sealing time. Any later question or window is "
                              "a new sealed version, never an edit of this one.",
        "genesis": v1_hash,
        "genesis_semantics": "WOW v1 closure pin identity, re-derived from the "
                             "v1 pin record on disk at seal time.",
        "v1_repository": "https://github.com/elekto-energy/eve-wow-v1",
        "v1_tag": "wow-v1.0",
        "documents": entries,
    }
    _, sc = determinism_check(canonical_bytes(seal_payload_out), "seal_payload")
    seal_hash = sha256_bytes(sc)
    print("determinism: OK")
    print("wow_v2_genesis_seal_hash: %s" % seal_hash)

    seal_file_out = os.path.join(root, SEAL_PATH.replace("/", os.sep))
    if not args.seal:
        print("STATUS: PREPARED - verify-only run, nothing written.")
        print("Sealing requires controller approval of the genesis record and")
        print("the discovery protocol, then rerun with --seal. No archive data")
        print("may be opened until the seal exists.")
        return
    if os.path.exists(seal_file_out):
        fail("%s already exists. Seals are immutable; not overwriting." % SEAL_PATH)
    record = {
        "seal_payload": seal_payload_out,
        "wow_v2_genesis_seal_hash": seal_hash,
        "sealed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "SEALED",
    }
    with open(seal_file_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2, sort_keys=False)
        f.write("\n")
    print("SEALED: wrote %s" % SEAL_PATH)
    print("Discovery questions are now frozen. Archive access may be prepared.")


if __name__ == "__main__":
    main()
