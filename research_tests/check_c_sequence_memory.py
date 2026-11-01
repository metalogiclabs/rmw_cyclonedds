#!/usr/bin/env python3
"""Compare actual ROS C sequence error paths; preserve UNKNOWNs honestly."""
import json
a=json.load(open("/evidence/baseline-c-sequence.json"))
b=json.load(open("/evidence/candidate-c-sequence.json"))
assert a["positive_control"]=="pass" and b["positive_control"]=="pass"
assert a["loaded_libraries"] and b["loaded_libraries"]
assert a["loaded_libraries"] != b["loaded_libraries"]
assert a["status"]!="accepted" and b["status"]!="accepted"
print("BASELINE:", json.dumps(a,sort_keys=True))
print("CANDIDATE:", json.dumps(b,sort_keys=True))
if a["error_message"] != b["error_message"]:
    print("DIFFERENTIAL: two distinct native error paths; inspect before claiming no allocation")
else:
    print("UNKNOWN: identical errors; this run does not prove reduced allocations")
print("BOUNDED: per-process virtual-memory headroom 5 MiB, no uncontrolled OOM test")
