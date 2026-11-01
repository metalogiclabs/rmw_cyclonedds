#!/usr/bin/env python3
"""Bounded native regression for nested CDR sequence allocation preflight."""
import json
import os
import resource
import struct

from rclpy.serialization import deserialize_message, serialize_message
from test_msgs.msg import BasicTypes, UnboundedSequences

# Positive controls: the sequence must retain its normal wire semantics.
for count in (0, 1, 2):
    message = UnboundedSequences(basic_types_values=[BasicTypes()] * count)
    roundtrip = deserialize_message(serialize_message(message), UnboundedSequences)
    assert len(roundtrip.basic_types_values) == count

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
          "positive_controls": "3/3 passed", "source_libs": paths,
          "virtual_memory_limit": cap, "outcome": outcome, "reason": reason}
print(json.dumps(result, sort_keys=True), flush=True)
assert outcome in ("RMWError", "RuntimeError"), result
assert "invalid data size" in reason, result
