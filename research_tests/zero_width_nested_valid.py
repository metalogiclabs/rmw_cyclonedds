#!/usr/bin/env python3
"""Native positive control: a sequence of zero-field ROS messages is legal CDR.

This is a valid-message compatibility test, not a malformed-input fuzz case.
Run independently with the packaged RMW and the source-built candidate.
"""
import json
import os
import sys

from rclpy.serialization import deserialize_message, serialize_message
from test_msgs.msg import Constants, UnboundedSequences

count = 256
result = {"case": "zero_field_nested_sequence", "count": count, "accepted": False}
try:
    original = UnboundedSequences(constants_values=[Constants() for _ in range(count)])
    wire = serialize_message(original)
    result["wire_bytes"] = len(wire)
    restored = deserialize_message(wire, UnboundedSequences)
    result["decoded_count"] = len(restored.constants_values)
    result["accepted"] = result["decoded_count"] == count
except Exception as exc:
    result["error_type"] = type(exc).__name__
    result["error"] = str(exc)[:400]
finally:
    paths = sorted({line.split()[-1] for line in open("/proc/self/maps")
                    if "librmw_cyclonedds_cpp.so" in line and "/" in line})
    result["loaded_libraries"] = paths
    expected = os.environ.get("EXPECTED_LIB_DIR", "")
    result["expected_library_dir"] = expected
    result["library_provenance_ok"] = bool(paths and expected and
                                            all(path.startswith(expected + "/")
                                                for path in paths))
    print(json.dumps(result, sort_keys=True), flush=True)

if not (result["accepted"] and result["library_provenance_ok"]):
    sys.exit(1)
