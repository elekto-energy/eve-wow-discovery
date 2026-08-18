#!/usr/bin/env python3
# wow_v2_d2_seal.py - seal for the D2 comparison-region amendment.
#
# WHAT THIS SEALS:
# The numerical bounds of the D2 LOCAL CONTEXT question, fixed before any
# N50CH archive content is inspected. DISCOVERY_PROTOCOL_v1 requires exactly
# this: the bounds must be specified and sealed in an amendment BEFORE
# inspection, and may not be widened, narrowed, shifted or adapted afterwards.
#
# ORDERING ENFORCEMENT:
# Gate 1 re-derives the WOW v1 closure identity from project 042_wow, which is
# READ ONLY from here. Gate 2 re-derives the WOW v2 genesis seal and checks it
# chains to that identity. Gate 3 re-reads DISCOVERY_PROTOCOL_v1 from disk and
# checks it still canonicalises to the value the genesis seal bound, which
# proves the frozen questions have not moved since sealing. Gate 4 checks the
# amendment binds all three of those identities and that every bound carries a
# value_basis. Only then may the amendment be sealed.
#
# HASH PROVENANCE RULE: the expected constants below are fail-hard
# cross-checks, never the source of truth. Every value used is re-derived
# from the artifact on disk at run time.
#
# STATUS SEMANTICS: sealed records carry pre_seal_status and no field named
# status. Current lifecycle state lives ONLY here, in seal_payload.decision.
#
# NO NEW MACHINERY: canonicalization, value-domain validation, determinism
# check, fail-hard and write-once behaviour are the WOW v1 primitives,
# unchanged.
#
# Default mode: verify only (writes nothing). --seal writes
# research/v2_genesis/D2_AMENDMENT_SEAL.json once and refuses to overwrite.
# Python 3 stdlib only.

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

EXPECTED_V1_CLOSURE_PIN = "679e3e48d7ac2ce8653d8e385248388883284828549151e99f00ba1df823c3ae"
EXPECTED_V2_GENESIS_SEAL = "17c4258d924675ddce4c39f056e63572086adab07a8b3551cce736871b6fb895"
EXPECTED_PROTOCOL_CANONICAL = "88563848c68afa3d494945e251d7597f55c274e0c1d8de76ecbbb818cd0e7706"
# If any wording of the amendment changes before sealing, this constant must be
# updated in the same edit. A mismatch is a finding to investigate, never to
# accept.
EXPECTED_D2_CANONICAL = "aca7a27817c40239078e025dcbb0981ab3f70a124fbbb50feeb28544c91e9931"

V1_PIN_RECORD_DEFAULT = os.path.join(
    "..", "042_wow", "research", "wow1_final", "WOW1_CLOSURE_PIN.json")
GENESIS_SEAL_RECORD = "research/v2_genesis/WOW_V2_GENESIS_SEAL.json"
PROTOCOL_RECORD = "research/v2_genesis/DISCOVERY_PROTOCOL_v1.json"
AMENDMENT_RECORD = "research/v2_genesis/D2_AMENDMENT_v1.json"
SEAL_PATH = "research/v2_genesis/D2_AMENDMENT_SEAL.json"

REQUIRED_BOUNDS = [
    "B1_declination_sky_window",
    "B2_frequency_channel_window",
    "B3_time_date_window",
    "B4_comparison_variables",
    "B5_missing_and_unreadable_records",
    "B6_wow_record_participation_in_parameter_selection",
    "B7_extent_and_stopping_rule",
]


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


def read_json(path, label):
    if not os.path.exists(path):
        fail("%s not found at %s" % (label, path))
    with open(path, "rb") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="WOW v2 D2 amendment seal")
    ap.add_argument("--seal", action="store_true", help="write the seal record")
    ap.add_argument("--root", default=None, help="project root")
    ap.add_argument("--v1-pin", default=None,
                    help="path to the WOW v1 closure pin record (read only)")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(args.root) if args.root else os.path.dirname(here)
    print("WOW v2 D2 amendment seal tool. Root: %s" % root)

    # GATE 1: WOW v1 closure identity, re-derived from the closed project.
    v1_pin_path = os.path.abspath(
        args.v1_pin if args.v1_pin else os.path.join(root, V1_PIN_RECORD_DEFAULT))
    v1 = json.loads(read_json(v1_pin_path, "WOW v1 closure pin").decode("utf-8"))
    v1_hash = sha256_bytes(canonical_bytes(v1.get("pin_payload", {})))
    if v1_hash != v1.get("wow1_closure_pin_hash") or v1_hash != EXPECTED_V1_CLOSURE_PIN:
        fail("re-derived WOW v1 closure identity %s != expected" % v1_hash)
    print("RE-DERIVE WOW v1 CLOSURE  PASS")

    # GATE 2: the WOW v2 genesis seal must exist and chain to it.
    gs_path = os.path.join(root, GENESIS_SEAL_RECORD.replace("/", os.sep))
    if not os.path.exists(gs_path):
        fail("%s does not exist. The discovery questions must be SEALED before "
             "their bounds may be sealed. Run scripts/wow_v2_genesis_seal.py "
             "--seal first." % GENESIS_SEAL_RECORD)
    gs = json.loads(read_json(gs_path, "genesis seal").decode("utf-8"))
    gs_payload = gs.get("seal_payload", {})
    gs_hash = sha256_bytes(canonical_bytes(gs_payload))
    if gs_hash != gs.get("wow_v2_genesis_seal_hash") or gs_hash != EXPECTED_V2_GENESIS_SEAL:
        fail("re-derived WOW v2 genesis seal %s != expected" % gs_hash)
    if gs_payload.get("genesis") != v1_hash:
        fail("WOW v2 genesis seal is not chained to this WOW v1 closure identity")
    if gs_payload.get("decision") != "WOW_V2_DISCOVERY_PROTOCOL_SEALED":
        fail("WOW v2 genesis seal does not record a sealed discovery protocol")
    print("RE-DERIVE v2 GENESIS SEAL PASS")

    # GATE 3: the frozen questions must not have moved since they were sealed.
    sealed_protocol_canonical = None
    for entry in gs_payload.get("documents", []):
        if entry.get("name") == "DISCOVERY_PROTOCOL_v1.json":
            sealed_protocol_canonical = entry.get("canonical_sha256")
    if sealed_protocol_canonical != EXPECTED_PROTOCOL_CANONICAL:
        fail("the genesis seal binds protocol canonical %s, not the expected "
             "value" % sealed_protocol_canonical)
    proto_raw = read_json(os.path.join(root, PROTOCOL_RECORD.replace("/", os.sep)),
                          "discovery protocol")
    proto_obj, proto_canon = determinism_check(proto_raw, PROTOCOL_RECORD)
    proto_hash = sha256_bytes(proto_canon)
    if proto_hash != sealed_protocol_canonical:
        fail("DISCOVERY_PROTOCOL_v1 on disk canonicalises to %s but the genesis "
             "seal bound %s - the frozen questions have moved since sealing, "
             "which is a finding to investigate, never to accept"
             % (proto_hash, sealed_protocol_canonical))
    print("FROZEN QUESTIONS UNMOVED  PASS")

    # GATE 4: the amendment itself.
    amd_raw = read_json(os.path.join(root, AMENDMENT_RECORD.replace("/", os.sep)),
                        "D2 amendment")
    amd_obj, amd_canon = determinism_check(amd_raw, AMENDMENT_RECORD)
    validate_values(amd_obj, AMENDMENT_RECORD)
    amd_hash = sha256_bytes(amd_canon)
    if amd_hash != EXPECTED_D2_CANONICAL:
        fail("D2 amendment canonical %s != expected %s - if the amendment was "
             "edited, the constant in this tool must be updated in the same "
             "edit" % (amd_hash, EXPECTED_D2_CANONICAL))
    if amd_obj.get("amends", {}).get("canonical_sha256") != proto_hash:
        fail("the amendment does not amend the protocol version on disk")
    bt = amd_obj.get("bound_to", {})
    if bt.get("wow_v2_genesis_seal") != gs_hash:
        fail("amendment bound_to.wow_v2_genesis_seal does not match the "
             "re-derived genesis seal")
    if bt.get("wow_v1_closure_pin") != v1_hash:
        fail("amendment bound_to.wow_v1_closure_pin does not match the "
             "re-derived v1 closure identity")
    bounds = amd_obj.get("bounds", {})
    if sorted(bounds.keys()) != sorted(REQUIRED_BOUNDS):
        fail("amendment bounds must be exactly %s; found %s"
             % (sorted(REQUIRED_BOUNDS), sorted(bounds.keys())))
    for name, body in bounds.items():
        if not isinstance(body, dict) or not body.get("value_basis"):
            fail("bound %s carries no value_basis. Every numerical bound must "
                 "identify its basis so that a controller choice can never be "
                 "mistaken for a derivation." % name)
    print("AMENDMENT BINDINGS        PASS")
    print("EVERY BOUND HAS A BASIS   PASS (%d bounds)" % len(bounds))
    print("")
    print("%s" % AMENDMENT_RECORD)
    print("  raw       %s" % sha256_bytes(amd_raw))
    print("  canonical %s" % amd_hash)

    seal_payload_out = {
        "schema": "wow-v2-d2-amendment-seal",
        "schema_version": "1",
        "decision": "WOW_V2_D2_COMPARISON_REGION_SEALED",
        "decision_semantics": "The D2 comparison region is fixed as of this "
                              "seal. No N50CH archive content had been opened "
                              "at sealing time. The bounds may not be widened, "
                              "narrowed, shifted or adapted in response to "
                              "observed archive content. Any search outside the "
                              "sealed region is a separate exploratory analysis "
                              "and is never reported as a D2 result.",
        "genesis": gs_hash,
        "genesis_semantics": "WOW v2 genesis seal identity, re-derived from disk "
                             "at seal time. It in turn chains to the WOW v1 "
                             "closure identity.",
        "wow_v1_closure_pin": v1_hash,
        "discovery_protocol_canonical": proto_hash,
        "documents": [
            {
                "name": os.path.basename(AMENDMENT_RECORD),
                "path": AMENDMENT_RECORD,
                "raw_sha256": sha256_bytes(amd_raw),
                "canonical_sha256": amd_hash,
            }
        ],
    }
    _, sc = determinism_check(canonical_bytes(seal_payload_out), "seal_payload")
    seal_hash = sha256_bytes(sc)
    print("determinism: OK")
    print("wow_v2_d2_amendment_seal_hash: %s" % seal_hash)

    seal_file_out = os.path.join(root, SEAL_PATH.replace("/", os.sep))
    if not args.seal:
        print("STATUS: PREPARED - verify-only run, nothing written.")
        print("Sealing requires controller approval of the bounds, then rerun")
        print("with --seal. No archive content may be inspected until this")
        print("seal exists.")
        return
    if os.path.exists(seal_file_out):
        fail("%s already exists. Seals are immutable; not overwriting." % SEAL_PATH)
    record = {
        "seal_payload": seal_payload_out,
        "wow_v2_d2_amendment_seal_hash": seal_hash,
        "sealed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "SEALED",
    }
    with open(seal_file_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, indent=2, sort_keys=False)
        f.write("\n")
    print("SEALED: wrote %s" % SEAL_PATH)
    print("The D2 comparison region is now fixed. Archive enumeration may")
    print("begin under the B7 read scope: date, time with reference, and")
    print("declination only.")


if __name__ == "__main__":
    main()
