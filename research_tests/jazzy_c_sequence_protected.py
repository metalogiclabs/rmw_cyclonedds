#!/usr/bin/env python3
"""Process-isolated valid and malformed CDR controls for C sequence ownership."""

import argparse
import json
import os
from pathlib import Path
import resource
import struct
import subprocess
import sys


SHORT_TYPES = (
    "Arrays", "Strings", "WStrings", "MultiNested",
    "BoundedSequences", "UnboundedSequences", "BasicTypes",
)
VALID_NAMES = (
    "basic", "arrays", "unbounded", "bounded", "nested",
    "wide", "constants", "defaults",
)


def check_library():
    mapped = sorted({
        line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
        if "/librmw_cyclonedds_cpp.so" in line and "/" in line
    })
    expected = os.environ["EXPECTED_LIB_DIR"]
    assert len(mapped) == 1 and mapped[0].startswith(expected + "/"), mapped
    return mapped[0]


def valid_message(name):
    from test_msgs.msg import (
        Arrays, BasicTypes, BoundedSequences, Constants, Defaults,
        MultiNested, UnboundedSequences, WStrings,
    )
    if name == "basic":
        return BasicTypes(int32_value=-17, uint64_value=2**64 - 1)
    if name == "arrays":
        return Arrays()
    if name == "unbounded":
        return UnboundedSequences(
            uint64_values=[0, 1, 2**64 - 1],
            string_values=["alpha", "", "β"],
            basic_types_values=[BasicTypes(int32_value=17)],
        )
    if name == "bounded":
        return BoundedSequences(
            uint64_values=[0, 1, 2**64 - 1],
            string_values=["abc", ""],
            basic_types_values=[BasicTypes(int32_value=-1)],
        )
    if name == "nested":
        return MultiNested(unbounded_sequence_of_unbounded_sequences=[
            UnboundedSequences(int32_values=[-1, 0, 1], string_values=["nested"]),
        ])
    if name == "wide":
        return WStrings(unbounded_sequence_of_wstrings=["alpha", "Ω", "漢", ""])
    if name == "constants":
        return Constants()
    if name == "defaults":
        return Defaults()
    raise ValueError(name)


def child(kind, value):
    from rclpy.serialization import deserialize_message, serialize_message
    import test_msgs.msg as messages

    vm_kb = next(int(line.split()[1]) for line in
                 Path("/proc/self/status").read_text().splitlines()
                 if line.startswith("VmSize:"))
    cap = vm_kb * 1024 + 64 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))

    if kind == "valid":
        instance = valid_message(value)
        wire = bytes(serialize_message(instance))
        for _ in range(5):
            decoded = deserialize_message(wire, type(instance))
            assert bytes(serialize_message(decoded)) == wire, "valid round-trip changed"
        result = "accepted"
    else:
        if kind == "short":
            message_type, length = value.rsplit(":", 1)
            wire = bytes(range(int(length)))
            msgtype = getattr(messages, message_type)
        elif kind == "count":
            msgtype = messages.UnboundedSequences
            wire = bytearray(serialize_message(msgtype()))
            offset = 4 + 14 * 4
            assert struct.unpack_from("<I", wire, offset)[0] == 0
            wire = wire[:offset + 4]
            struct.pack_into("<I", wire, offset, 131072)
        else:
            raise ValueError(kind)
        try:
            deserialize_message(wire, msgtype)
        except Exception as exc:
            assert type(exc).__name__ == "RMWError", repr(exc)
            result = "defined_error"
        else:
            raise AssertionError(f"Malformed {kind} input unexpectedly accepted")

    print("PROTECTED_RESULT " + json.dumps({
        "kind": kind, "value": value, "result": result,
        "loaded_library": check_library(), "wire_bytes": len(wire),
    }, sort_keys=True), flush=True)


def parent():
    cases = [("valid", name) for name in VALID_NAMES]
    cases += [("short", f"{name}:{size}") for name in SHORT_TYPES for size in range(4)]
    cases += [("count", "inflated_131072")]
    rows = []
    for kind, value in cases:
        command = [sys.executable, __file__, "--child", kind, "--value", value]
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=15,
                               env=os.environ.copy(), check=False)
            markers = [line[len("PROTECTED_RESULT "):]
                       for line in p.stdout.splitlines()
                       if line.startswith("PROTECTED_RESULT ")]
            if p.returncode == 0 and len(markers) == 1:
                row = json.loads(markers[0])
                row["outcome"] = "pass"
            else:
                row = {"kind": kind, "value": value, "outcome": "failed",
                       "exit_code": p.returncode, "stderr": p.stderr[-1500:],
                       "stdout": p.stdout[-500:]}
        except subprocess.TimeoutExpired:
            row = {"kind": kind, "value": value, "outcome": "timeout"}
        rows.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)

    Path("/evidence/protected-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    failures = [row for row in rows if row["outcome"] != "pass"]
    if failures:
        raise SystemExit(f"FAIL: {len(failures)} of {len(rows)} protected controls")
    print(f"PASS: {len(rows)}/{len(rows)} protected valid/malformed controls", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", choices=("valid", "short", "count"))
    parser.add_argument("--value")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.value)
    else:
        parent()
