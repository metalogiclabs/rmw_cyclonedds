#!/usr/bin/env python3
"""Bounded, source-native ROS Jazzy peak-RSS differential (research only).

Each input runs in a fresh child; wait4 gives that child's true maximum RSS.
The forged sequence length has no corresponding serialized element bytes.
"""

import collections
import hashlib
import json
import os
import resource
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

COUNTS = (32768, 65536, 131072, 262144)
REPEATS = 5
TIMEOUT_SECONDS = 8
MAX_EXTRA_VIRTUAL_BYTES = 48 * 1024 * 1024


def make_wire(kind, count):
    from rclpy.serialization import serialize_message
    from test_msgs.msg import BasicTypes, UnboundedSequences

    if kind == "valid":
        msg = UnboundedSequences(
            basic_types_values=[BasicTypes(int32_value=i * 19) for i in range(8)]
        )
        return bytes(serialize_message(msg)), UnboundedSequences

    assert kind == "inflated_basic_count" and count in COUNTS
    wire = bytes(serialize_message(UnboundedSequences()))
    offset = 4 + 14 * 4  # CDR header and 14 preceding empty sequence lengths.
    assert len(wire) >= offset + 4, "unexpected message layout"
    assert struct.unpack_from("<I", wire, offset)[0] == 0, "unexpected count offset"
    forged = bytearray(wire[:offset + 4])
    struct.pack_into("<I", forged, offset, count)
    return bytes(forged), UnboundedSequences


def run_child(kind, count):
    from rclpy.serialization import deserialize_message, serialize_message

    wire, msgtype = make_wire(kind, count)
    wire_hash = hashlib.sha256(wire).hexdigest()

    # Relative per-process cap avoids a library-specific fixed VmSize baseline.
    vm_kb = next(
        int(line.split()[1]) for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith("VmSize:")
    )
    cap = vm_kb * 1024 + MAX_EXTRA_VIRTUAL_BYTES
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    try:
        parsed = deserialize_message(wire, msgtype)
        outcome, detail = "accepted", "deserialized"
        if kind == "valid":
            assert bytes(serialize_message(parsed)) == wire, "valid control changed"
    except Exception as exc:
        outcome, detail = "error", type(exc).__name__

    loaded = sorted({
        line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
        if "/librmw_cyclonedds_cpp.so" in line and "/" in line
    })
    expected = os.environ["EXPECTED_LIB_DIR"]
    assert loaded and all(path.startswith(expected + "/") for path in loaded), (loaded, expected)
    print("PEAK_RSS_RESULT " + json.dumps({
        "kind": kind, "count": count, "outcome": outcome, "detail": detail,
        "wire_bytes": len(wire), "wire_sha256": wire_hash,
        "as_limit_bytes": cap, "as_headroom_bytes": MAX_EXTRA_VIRTUAL_BYTES,
        "loaded_library": loaded[0],
    }), flush=True)


def spawn_and_wait(cmd, env):
    """Capture one child's exit status and isolated peak RSS, including on signal."""
    with tempfile.TemporaryFile(mode="w+t") as stdout, tempfile.TemporaryFile(mode="w+t") as stderr:
        process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, env=env)
        deadline = time.monotonic() + TIMEOUT_SECONDS
        timed_out = False
        while True:
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                break
            if time.monotonic() >= deadline:
                timed_out = True
                process.kill()
                _, status, usage = os.wait4(process.pid, 0)
                break
            time.sleep(0.02)
        process.returncode = os.waitstatus_to_exitcode(status)
        stdout.seek(0)
        stderr.seek(0)
        return {
            "exit_code": process.returncode, "timeout": timed_out,
            "peak_rss_kib": usage.ru_maxrss, "stdout": stdout.read(),
            "stderr": stderr.read()[-3000:],
        }


def run_parent():
    arm = os.environ["ARM"]
    rows = []
    cases = [("valid", 8)] + [("inflated_basic_count", n) for n in COUNTS]
    for kind, count in cases:
        for repetition in range(REPEATS):
            result = spawn_and_wait(
                [sys.executable, __file__, "child", kind, str(count)], os.environ.copy()
            )
            row = {
                "arm": arm, "kind": kind, "count": count,
                "repeat": repetition, "peak_rss_kib": result["peak_rss_kib"],
                "exit_code": result["exit_code"], "timeout": result["timeout"],
            }
            if result["timeout"]:
                row.update(outcome="timeout", detail=result["stderr"])
            elif result["exit_code"] != 0:
                row.update(outcome="harness_failure", detail=result["stderr"])
            else:
                markers = [line.removeprefix("PEAK_RSS_RESULT ") for line in
                           result["stdout"].splitlines() if line.startswith("PEAK_RSS_RESULT ")]
                if len(markers) != 1:
                    row.update(outcome="harness_failure", detail=result["stdout"][-500:])
                else:
                    row.update(json.loads(markers[0]))
            rows.append(row)
            print(json.dumps(row, sort_keys=True), flush=True)

    Path(f"/evidence/{arm}-peak-rss.json").write_text(json.dumps(rows, indent=2) + "\n")
    for kind, count in cases:
        subset = [r for r in rows if r["kind"] == kind and r["count"] == count]
        vals = [r["peak_rss_kib"] for r in subset]
        print(json.dumps({"arm": arm, "kind": kind, "count": count,
                          "rss_min_kib": min(vals), "rss_median_kib": statistics.median(vals),
                          "rss_max_kib": max(vals),
                          "outcomes": dict(collections.Counter(r["outcome"] for r in subset))}), flush=True)
    assert all(r["outcome"] == ("accepted" if r["kind"] == "valid" else "error")
               for r in rows), "invalid control, crash, timeout or harness failure"


def selftest():
    result = spawn_and_wait([sys.executable, __file__, "selftest-child"], os.environ.copy())
    assert result["exit_code"] == 0 and result["peak_rss_kib"] > 0, result
    assert "selftest-child-ok" in result["stdout"], result
    print("wait4 resource capture self-test OK")


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "selftest":
        selftest()
    elif len(sys.argv) == 2 and sys.argv[1] == "selftest-child":
        print("selftest-child-ok")
    elif len(sys.argv) == 1:
        run_parent()
    elif len(sys.argv) == 4 and sys.argv[1] == "child":
        run_child(sys.argv[2], int(sys.argv[3]))
    else:
        sys.exit("usage: jazzy_peak_rss.py [selftest|child KIND COUNT]")
