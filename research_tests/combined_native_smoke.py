#!/usr/bin/env python3
"""Native ROS Jazzy smoke for a bounded CDR sequence-count negative control."""
import json
import os
import resource
import struct
from rclpy.serialization import deserialize_message, serialize_message
from test_msgs.msg import Arrays, BasicTypes, Strings, UnboundedSequences

controls = ["Arrays", "BasicTypes", "Strings", "UnboundedSequences"]
types = {t.__name__: t for t in (Arrays, BasicTypes, Strings, UnboundedSequences)}
for name in controls:
    cls = types[name]
    assert isinstance(deserialize_message(serialize_message(cls()), cls), cls), name
paths = sorted({line.split()[-1] for line in open("/proc/self/maps")
               if "librmw_cyclonedds_cpp.so" in line and "/" in line})
expected = os.environ["EXPECTED_LIB_DIR"]
assert paths and all(p.startswith(expected) for p in paths), paths

# Four empty primitive sequences precede the float64 sequence in this test
# message. The declared float64 element count needs 8 MiB of payload, but the
# supplied payload is only 1 MiB; do not let the process request 8 MiB.
n = 1 << 20
wire = b"\x00\x01\x00\x00" + b"\x00" * 16 + struct.pack("<I", n) + b"\x00" * n
vm_kb = next(int(line.split()[1]) for line in open("/proc/self/status")
             if line.startswith("VmSize:"))
cap = vm_kb * 1024 + 5 * 1024 * 1024
resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
outcome = "accepted"
reason = ""
try:
    deserialize_message(wire, UnboundedSequences)
except Exception as exc:
    outcome = type(exc).__name__
    reason = str(exc)[:300]
result = {"controls": controls, "source": "source-built Jazzy fork",
          "loaded_libs": paths, "malformed_outcome": outcome,
          "malformed_error": reason, "input_size": len(wire),
          "declared_float64_count": n, "virtual_memory_limit": cap}
print(json.dumps(result, sort_keys=True), flush=True)
assert outcome in ("RMWError", "RuntimeError"), result
