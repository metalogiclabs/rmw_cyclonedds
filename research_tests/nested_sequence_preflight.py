#!/usr/bin/env python3
"""Bounded native regression for nested CDR sequence allocation preflight."""
import json
import os
import resource
import struct

from rclpy.serialization import deserialize_message, serialize_message
from test_msgs.msg import BasicTypes, Constants, Defaults, UnboundedSequences

# Positive controls include a zero-member nested message (Constants),
# non-empty primitive-only nested messages, and default-valued messages.
cases = [
    ("empty", {"basic_types_values": []}, "basic_types_values", 0),
    ("one_basic", {"basic_types_values": [BasicTypes()]}, "basic_types_values", 1),
    ("two_basic", {"basic_types_values": [BasicTypes(), BasicTypes()]}, "basic_types_values", 2),
    ("empty_member_type", {"constants_values": [Constants(), Constants()]}, "constants_values", 2),
    ("defaults", {"defaults_values": [Defaults()]}, "defaults_values", 1),
]
for label, fields, name, count in cases:
    message = UnboundedSequences(**fields)
    roundtrip = deserialize_message(serialize_message(message), UnboundedSequences)
    assert len(getattr(roundtrip, name)) == count, label

paths = sorted({line.split()[-1] for line in open("/proc/self/maps")
                if "librmw_cyclonedds_cpp.so" in line and "/" in line})
expected = os.environ["EXPECTED_LIB_DIR"]
assert paths and all(path.startswith(expected) for path in paths), paths

# In test_msgs/UnboundedSequences, 14 primitive/string sequences precede
# basic_types_values. Each preceding sequence is empty (4-byte count).
# BasicTypes has 45 bytes of scalar fields *before* CDR alignment padding.
# The declared 131072 elements cannot fit in the 131072 following bytes.
count = 1 << 17
wire = (b"\x00\x01\x00\x00" + b"\x00" * (14 * 4)
        + struct.pack("<I", count) + b"\x00" * count)
vm_kb = next(int(line.split()[1]) for line in open("/proc/self/status")
             if line.startswith("VmSize:"))
cap = vm_kb * 1024 + 2 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
outcome = "accepted"
reason = ""
try:
    deserialize_message(wire, UnboundedSequences)
except Exception as exc:
    outcome = type(exc).__name__
    reason = str(exc)[:400]
result = {"input_bytes": len(wire), "declared_nested_elements": count,
          "positive_controls": "5/5 passed", "source_libs": paths,
          "virtual_memory_limit": cap, "outcome": outcome, "reason": reason}
print(json.dumps(result, sort_keys=True), flush=True)
assert outcome in ("RMWError", "RuntimeError"), result
assert "invalid data size" in reason, result
