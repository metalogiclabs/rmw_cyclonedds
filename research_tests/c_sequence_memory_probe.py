#!/usr/bin/env python3
"""Bounded, actual rmw_cyclonedds Jazzy malformed-sequence allocation check."""
import json, os, resource, struct, sys
from rclpy.serialization import serialize_message, deserialize_message
from test_msgs.msg import UnboundedSequences

valid=serialize_message(UnboundedSequences())
assert type(deserialize_message(valid,UnboundedSequences)) is UnboundedSequences
loaded=sorted({s.split()[-1] for s in open("/proc/self/maps")
                if "librmw_cyclonedds_cpp.so" in s and "/" in s})
assert loaded and all(p.startswith(os.environ["EXPECTED_LIB_DIR"]) for p in loaded), loaded

# First four sequence fields have zero elements: bool, byte, char, float32.
# Fifth is float64. Claim 1 Mi elements while supplying just 1 Mi B, short
# of the minimum 8 Mi B needed. The 2 Mi B total process input limit is finite.
size = 1<<20
data = b"\x00\x01\x00\x00" + b"\x00"*16 + struct.pack("<I",size) + b"\x00"*size
# Cap virtual-memory growth just above the already-initialized ROS process.
# A 1M x float64 allocation (8 MiB) is beyond this 5 MiB headroom.
vm_kb=next(int(line.split()[1]) for line in open("/proc/self/status")
           if line.startswith("VmSize:"))
limit_bytes=vm_kb*1024+5*1024*1024
resource.setrlimit(resource.RLIMIT_AS,(limit_bytes,limit_bytes))
before=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
status="none"
error_message=""
try:
    deserialize_message(data,UnboundedSequences)
    status="accepted"
except Exception as e:
    status=type(e).__name__
    error_message=str(e)[:300]
after=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
result={"arm":os.environ["ARM"],"case":"float64_C_sequence_truncated",
        "input_bytes":len(data),"declared_elements":size,
        "status":status,"error_message":error_message,"vm_limit_bytes":limit_bytes,"peak_rss_kb_before":before,"peak_rss_kb_after":after,
        "peak_delta_kb":after-before,"loaded_libraries":loaded,
        "positive_control":"pass"}
print(json.dumps(result,sort_keys=True),flush=True)
assert status in ("RMWError", "RuntimeError"),result
