#!/usr/bin/env python3
"""Verify identical native C++ inputs and summarize requests versus memory use."""
import collections
import json
import statistics
from pathlib import Path

EVIDENCE = Path("/evidence")
REPEATS = 5
CASES = [("valid", 8), ("malformed", 8192),
         ("malformed", 65536), ("malformed", 262144)]


def main():
    results = {}
    for arm in ("base", "candidate"):
        for mode, count in CASES:
            for i in range(REPEATS):
                key = (arm, mode, count, i)
                file = EVIDENCE / f"{arm}-{mode}-{count}-{i}.txt"
                markers = [line.removeprefix("METRIC ") for line in file.read_text().splitlines()
                           if line.startswith("METRIC ")]
                assert len(markers) == 1, (file, markers)
                row = json.loads(markers[0])
                assert row["mode"] == mode and row["count"] == count, (file, row)
                assert row["rejected"] == (mode == "malformed"), (file, row)
                assert row["library"].startswith(f"/tmp/install-{arm}/lib/"), row
                assert row["ru_maxrss_after_kib"] >= row["ru_maxrss_before_kib"], row
                assert row["vmpeak_kib"] >= row["vmsize_before_kib"], row
                assert row["max_new_request_bytes"] >= 0
                results[key] = row
    summary = []
    for mode, count in CASES:
        for i in range(REPEATS):
            left = results["base", mode, count, i]
            right = results["candidate", mode, count, i]
            assert (left["wire_fnv1a64"], left["wire_bytes"]) == (
                right["wire_fnv1a64"], right["wire_bytes"]), (mode, count, i)
        row = {"mode": mode, "count": count, "repeats": REPEATS,
               "wire_bytes": results["base", mode, count, 0]["wire_bytes"]}
        for arm in ("base", "candidate"):
            trial = [results[arm, mode, count, i] for i in range(REPEATS)]
            for metric in ("max_new_request_bytes", "total_new_requested_bytes",
                           "vmpeak_kib", "ru_maxrss_after_kib",
                           "vmrss_after_kib", "vmrss_before_kib"):
                values = [x[metric] for x in trial]
                row[f"{arm}_{metric}_min"] = min(values)
                row[f"{arm}_{metric}_median"] = statistics.median(values)
                row[f"{arm}_{metric}_max"] = max(values)
        for metric in ("max_new_request_bytes", "vmpeak_kib", "ru_maxrss_after_kib"):
            row[f"median_{metric}_reduction"] = (
                row[f"base_{metric}_median"] - row[f"candidate_{metric}_median"])
        summary.append(row)
    payload = {"trials_per_arm": len(CASES) * REPEATS, "total_executions": 2 * len(CASES) * REPEATS,
               "all_valid_controls_pass": True, "all_malformed_defined_errors": True,
               "metrics": "C++ operator new requests, Linux VmPeak/VmRSS and getrusage ru_maxrss",
               "source_delta": "PR629 preflight only; PR625 applied to both arms",
               "limitations": ["Not the original issue #619 fuzz seed",
                               "operator new tracing does not instrument C malloc/calloc/realloc",
                               "VmPeak/RSS include process runtime and may not isolate a transient allocation"],
               "comparisons": summary}
    (EVIDENCE / "allocator-residency-comparison.json").write_text(json.dumps(payload, indent=2) + "\n")
    (EVIDENCE / "allocator-residency-trials.json").write_text(json.dumps([
        {"arm": key[0], "repeat": key[3], **value} for key, value in sorted(results.items())
    ], indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
