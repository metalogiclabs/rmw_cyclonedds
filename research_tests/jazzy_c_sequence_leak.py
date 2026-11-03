#!/usr/bin/env python3
"""Finite source-native rclpy / C-typesupport sequence-ownership regression.

Each type is deserialized repeatedly in its own capped child process. The test
checks actual resident growth, not a mock allocator or source-text pattern.
"""

import argparse
import gc
import json
import os
from pathlib import Path
import resource
import subprocess
import sys


MESSAGE_CLASSES = (
    "Arrays",
    "BoundedSequences",
    "UnboundedSequences",
    "Strings",
    "WStrings",
    "MultiNested",
)
GROWTH_LIMIT_BYTES_PER_CALL = 64.0
RELATIVE_VIRTUAL_LIMIT = 384 * 1024 * 1024


def proc_kib(field):
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1])
    raise RuntimeError(f"No {field} field in /proc/self/status")


def loaded_cyclone_library():
    paths = sorted({
        line.split()[-1]
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "/librmw_cyclonedds_cpp.so" in line and "/" in line
    })
    expected = os.environ["EXPECTED_LIB_DIR"]
    if len(paths) != 1 or not paths[0].startswith(expected + "/"):
        raise RuntimeError(f"Unexpected loaded library: {paths}; expected {expected}")
    return paths[0]


def child(message_name, count):
    from rclpy.serialization import deserialize_message, serialize_message
    import test_msgs.msg as messages

    message_type = getattr(messages, message_name)
    wire = bytes(serialize_message(message_type()))
    # A successful valid round-trip is a prerequisite to interpreting RSS.
    assert bytes(serialize_message(deserialize_message(wire, message_type))) == wire

    for _ in range(1000):
        deserialize_message(wire, message_type)
    gc.collect()
    library = loaded_cyclone_library()
    vm_limit = proc_kib("VmSize") * 1024 + RELATIVE_VIRTUAL_LIMIT
    resource.setrlimit(resource.RLIMIT_AS, (vm_limit, vm_limit))
    resource.setrlimit(resource.RLIMIT_CPU, (50, 50))

    samples = [proc_kib("VmRSS")]
    stride = count // 4
    assert stride > 0 and count % stride == 0
    for index in range(count):
        deserialize_message(wire, message_type)
        if (index + 1) % stride == 0:
            gc.collect()
            samples.append(proc_kib("VmRSS"))
    growth = (samples[-1] - samples[0]) * 1024 / count
    print("C_SEQUENCE_RESULT " + json.dumps({
        "message_type": message_name,
        "calls": count,
        "wire_bytes": len(wire),
        "loaded_library": library,
        "rss_samples_kib": samples,
        "bytes_per_call": round(growth, 3),
        "vm_cap_bytes": vm_limit,
    }, sort_keys=True), flush=True)


def suite(count, arm):
    rows = []
    for message_name in MESSAGE_CLASSES:
        cmd = [sys.executable, __file__, "--child", message_name, "--count", str(count)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                    env=os.environ.copy(), check=False)
            markers = [line[len("C_SEQUENCE_RESULT "):]
                       for line in result.stdout.splitlines()
                       if line.startswith("C_SEQUENCE_RESULT ")]
            if result.returncode != 0 or len(markers) != 1:
                row = {"message_type": message_name, "outcome": "harness_failure",
                       "exit_code": result.returncode,
                       "stdout": result.stdout[-1000:], "stderr": result.stderr[-1500:]}
            else:
                row = json.loads(markers[0])
                row["outcome"] = ("pass" if row["bytes_per_call"] <=
                                  GROWTH_LIMIT_BYTES_PER_CALL else "leak")
        except subprocess.TimeoutExpired:
            row = {"message_type": message_name, "outcome": "timeout"}
        row["arm"] = arm
        rows.append(row)
        print(json.dumps(row, sort_keys=True), flush=True)

    Path(f"/evidence/{arm}-c-sequence-results.json").write_text(
        json.dumps(rows, indent=2) + "\n")
    failures = [row["message_type"] for row in rows if row["outcome"] != "pass"]
    if failures:
        raise SystemExit("FAIL: C sequence lifetime regression: " + ", ".join(failures))
    print(f"PASS: all {len(rows)} finite C sequence lifetime controls", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--child")
    parser.add_argument("--count", type=int, default=20000)
    parser.add_argument("--arm", default="source")
    args = parser.parse_args()
    if args.child:
        child(args.child, args.count)
    else:
        suite(args.count, args.arm)
