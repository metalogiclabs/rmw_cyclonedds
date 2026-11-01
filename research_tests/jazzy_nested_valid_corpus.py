#!/usr/bin/env python3
"""Source-native, deterministic valid nested-message corpus for Jazzy Cyclone DDS.

A positive-control test of the conservative recursive lower bound.  No private
inputs, network services or flight hardware.  Unexpected acceptances/rejections
are fatal rather than silently skipped.
"""
import json
import os
from pathlib import Path

from rclpy.serialization import serialize_message, deserialize_message
from test_msgs.msg import (
    BasicTypes, Constants, Defaults, Arrays, BoundedSequences,
    UnboundedSequences, MultiNested,
)

expected_dir = os.environ["EXPECTED_LIB_DIR"]
records = []
types = [BasicTypes, Constants, Defaults, Arrays, BoundedSequences,
         UnboundedSequences, MultiNested]

def check(msg, name, field=None, expected_count=None):
    wire = bytes(serialize_message(msg))
    received = deserialize_message(wire, type(msg))
    assert isinstance(received, type(msg)), name
    assert bytes(serialize_message(received)) == wire, name
    if field is not None:
        assert len(getattr(received, field)) == expected_count, (name, field)
        assert list(getattr(received, field)) == list(getattr(msg, field)), name
    records.append({"name": name, "class": type(msg).__name__,
                    "bytes": len(wire), "field": field, "count": expected_count})

for cls in types:
    check(cls(), "default_" + cls.__name__)

nested = [
    ("basic_types_values", BasicTypes),
    ("constants_values", Constants),
    ("defaults_values", Defaults),
]
fields = UnboundedSequences.get_fields_and_field_types()
assert all(name in fields for name, _ in nested), fields

for field, cls in nested:
    for n in (0, 1, 2, 3, 4, 8, 16, 32, 128):
        vals = [cls() for _ in range(n)]
        if cls is BasicTypes:
            for i, obj in enumerate(vals):
                obj.int32_value = i * 17 - 500
                obj.bool_value = (i % 2 == 1)
        msg = UnboundedSequences(**{field: vals})
        check(msg, "nested_" + field + "_count_" + str(n), field, n)

for a,b,c in ((0,0,0),(1,2,3),(3,1,2),(16,8,4)):
    msg=UnboundedSequences(
        basic_types_values=[BasicTypes() for _ in range(a)],
        constants_values=[Constants() for _ in range(b)],
        defaults_values=[Defaults() for _ in range(c)],
    )
    for field,n in (("basic_types_values",a),("constants_values",b),
                    ("defaults_values",c)):
        check(msg,"mixed_"+str((a,b,c))+"_"+field,field,n)

assert len(records)==46, len(records)
paths=sorted({line.split()[-1] for line in open("/proc/self/maps")
              if "/librmw_cyclonedds_cpp.so" in line and "/" in line})
assert paths and all(p.startswith(expected_dir) for p in paths), paths
report={"status":"PASS","cases":len(records),"libraries":paths,
        "message_classes":[cls.__name__ for cls in types],
        "nested_fields":fields,"min_bytes":min(r["bytes"] for r in records),
        "max_bytes":max(r["bytes"] for r in records),
        "records":records}
out=Path("/evidence/valid-nested-corpus.json")
out.write_text(json.dumps(report,indent=2,sort_keys=True))
print(json.dumps({k:v for k,v in report.items() if k != "records"},sort_keys=True))
