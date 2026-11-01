#!/usr/bin/env python3
"""Validate pinned-arm RSS runs and describe measured differences, not fixes."""

import json
import statistics
from pathlib import Path

COUNTS = (32768, 65536, 131072, 262144)
REPEATS = 5


def check(evidence=Path("/evidence")):
    arms = {arm: json.loads((evidence / f"{arm}-peak-rss.json").read_text())
            for arm in ("base", "candidate")}
    expected = {("valid", 8, i) for i in range(REPEATS)} | {
        ("inflated_basic_count", n, i) for n in COUNTS for i in range(REPEATS)
    }
    by_arm = {}
    for arm, rows in arms.items():
        assert len(rows) == len(expected), (arm, len(rows))
        lookup = {(r["kind"], r["count"], r["repeat"]): r for r in rows}
        assert set(lookup) == expected, (arm, "missing or duplicate cases")
        for key, row in lookup.items():
            assert row["arm"] == arm
            assert row["outcome"] == ("accepted" if key[0] == "valid" else "error"), row
            assert row["exit_code"] == 0 and not row["timeout"], row
            assert row["peak_rss_kib"] > 0
            assert row["as_headroom_bytes"] == 48 * 1024 * 1024
            assert row["loaded_library"].startswith(f"/tmp/install-{arm}/lib/"), row
        by_arm[arm] = lookup

    comparisons = []
    for key in sorted(expected):
        a, b = by_arm["base"][key], by_arm["candidate"][key]
        assert a["wire_sha256"] == b["wire_sha256"] and a["wire_bytes"] == b["wire_bytes"], key
    for kind, count in [("valid", 8)] + [("inflated_basic_count", n) for n in COUNTS]:
        result = {"kind": kind, "count": count, "repeats": REPEATS}
        for arm in ("base", "candidate"):
            values = [by_arm[arm][kind, count, i]["peak_rss_kib"] for i in range(REPEATS)]
            result[arm + "_min_rss_kib"] = min(values)
            result[arm + "_median_rss_kib"] = statistics.median(values)
            result[arm + "_max_rss_kib"] = max(values)
        result["median_reduction_kib"] = result["base_median_rss_kib"] - result["candidate_median_rss_kib"]
        comparisons.append(result)
    summary = {"arms": list(arms), "trials_per_arm": len(expected),
               "valid_per_arm": REPEATS, "malformed_per_arm": 4 * REPEATS,
               "unit": "KiB", "metric": "wait4 per-child ru_maxrss",
               "comparisons": comparisons,
               "caveat": "Per-child peak RSS is not a maximum allocation request, and this bounded corpus does not reproduce the original >20GB fuzzing report."}
    (evidence / "peak-rss-comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    check()
