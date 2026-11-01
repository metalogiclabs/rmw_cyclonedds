#!/usr/bin/env python3
"""Deterministic ROS Jazzy metamorphic CDR corpus, isolated under memory limits.

No fuzzed I/O, no external systems. Baseline and candidate share every case.
Only source-pinned and process-isolated results can count as comparative evidence.
"""
import collections
import json
import os
import resource
import struct
import subprocess
import sys

FAMILIES = ["basic", "constants", "defaults", "strings", "uint64", "float64", "mixed"]
COUNTS = [0, 1, 2, 3, 4, 8, 16, 32, 64]
DEFAULTS = ["Arrays", "BasicTypes", "Strings", "WStrings", "BoundedSequences", "MultiNested", "UnboundedSequences"]
VARIANTS = ["valid", "cut_1", "cut_half", "cut_last", "cut_header", "large_count"]
CASES = (
    [(f, n, v) for f in FAMILIES for n in COUNTS for v in VARIANTS[:-1]]
    + [("default_"+t, 0, v) for t in DEFAULTS for v in VARIANTS[:-1]]
    + [("basic", n, "large_count") for n in COUNTS]
)

def message(family, n):
    import test_msgs.msg as m
    if family.startswith("default_"):
        return getattr(m, family.removeprefix("default_"))()
    if family == "basic":
        vals = [m.BasicTypes(int32_value=i*17 - 400, bool_value=(i % 2 == 1)) for i in range(n)]
        return m.UnboundedSequences(basic_types_values=vals)
    if family == "constants":
        return m.UnboundedSequences(constants_values=[m.Constants() for _ in range(n)])
    if family == "defaults":
        return m.UnboundedSequences(defaults_values=[m.Defaults() for _ in range(n)])
    if family == "strings":
        return m.UnboundedSequences(string_values=[("", "a", "hello", "\u00e9")[i % 4] for i in range(n)])
    if family == "uint64":
        return m.UnboundedSequences(uint64_values=[i*11 for i in range(n)])
    if family == "float64":
        return m.UnboundedSequences(float64_values=[float(i)/4 for i in range(n)])
    if family == "mixed":
        return m.UnboundedSequences(
            basic_types_values=[m.BasicTypes(int32_value=i) for i in range(n)],
            constants_values=[m.Constants() for _ in range(n // 2)],
            defaults_values=[m.Defaults() for _ in range(n // 3)],
            string_values=["a"] * (n // 4))
    raise ValueError(family)

def child(family, n, variant):
    from rclpy.serialization import deserialize_message, serialize_message
    msg = message(family, n)
    full = bytes(serialize_message(msg))
    if variant == "valid":
        wire = full
    elif variant == "cut_1":
        wire = full[:1]
    elif variant == "cut_half":
        wire = full[:len(full)//2]
    elif variant == "cut_last":
        wire = full[:-1]
    elif variant == "cut_header":
        wire = full[:4]
    elif variant == "large_count":
        assert family == "basic"
        wire = bytearray(full)
        # 14 preceding empty sequence fields, each encoded by a uint32 length.
        # This was source-pinned by the earlier nested probe, not inferred from output.
        offset = 4 + 14*4
        assert len(wire) >= offset+4
        assert struct.unpack_from("<I", wire, offset)[0] == n, "sequence layout changed"
        struct.pack_into("<I",wire,offset,1<<20)
        wire = bytes(wire)
    else:
        raise ValueError(variant)
    if variant != "valid":
        vm_kb = next(int(z.split()[1]) for z in open("/proc/self/status") if z.startswith("VmSize:"))
        cap=vm_kb * 1024 + 24*1024*1024
        resource.setrlimit(resource.RLIMIT_AS,(cap,cap))
        resource.setrlimit(resource.RLIMIT_CPU,(3,3))
    try:
        parsed=deserialize_message(wire,type(msg))
        outcome="accepted"
        if variant=="valid":
            assert bytes(serialize_message(parsed)) == full, "noncanonical valid roundtrip"
    except Exception as exc:
        outcome="error"
        detail=type(exc).__name__
        if variant=="valid":
            raise
    else:
        detail="roundtrip" if variant == "valid" else "deserializer accepted"
    paths=sorted({z.split()[-1] for z in open("/proc/self/maps") if "/librmw_cyclonedds_cpp.so" in z and "/" in z})
    expected=os.environ["EXPECTED_LIB_DIR"]
    assert paths and all(p.startswith(expected) for p in paths),(paths,expected)
    print(json.dumps({"outcome":outcome,"detail":detail,"input_len":len(wire),"valid_len":len(full),
                      "library":paths[0]}),flush=True)

def parent():
    data=[]
    for i,(family,n,variant) in enumerate(CASES):
        cmd=[sys.executable,__file__,"child",family,str(n),variant]
        try:
            res=subprocess.run(cmd,capture_output=True,text=True,timeout=5,env=os.environ)
            if res.returncode<0:
                outcome="signal";detail="signal "+str(-res.returncode)
            elif res.returncode>0:
                outcome="harness_error";detail=res.stderr[-1000:]
            else:
                v=json.loads(res.stdout.strip().splitlines()[-1])
                outcome=v["outcome"];detail=v
        except subprocess.TimeoutExpired:
            outcome="timeout";detail=">5s"
        except (ValueError,KeyError,IndexError) as exc:
            outcome="harness_error";detail=str(exc)
        row={"index":i,"family":family,"count":n,"variant":variant,"outcome":outcome,"detail":detail}
        data.append(row)
        if outcome not in ("accepted","error"):
            print(json.dumps({"unexpected":row}),flush=True)
    import pathlib
    arm=os.environ["ARM"]
    pathlib.Path("/evidence/"+arm+"-metamorphic.json").write_text(json.dumps(data,indent=2))
    totals=dict(collections.Counter(r["outcome"] for r in data))
    print(json.dumps({"arm":arm,"cases":len(data),"totals":totals}),flush=True)
    assert all(r["outcome"]=="accepted" for r in data if r["variant"]=="valid"),"valid control failed"
    assert all(r["outcome"]=="error" for r in data if r["variant"] in ("cut_1","large_count")),"strict malformed control failed"
    assert all(r["outcome"] in ("accepted","error") for r in data),"crash, timeout or harness error"
if __name__=="__main__":
    if len(sys.argv)==1: parent()
    elif len(sys.argv)==5 and sys.argv[1]=="child":child(sys.argv[2],int(sys.argv[3]),sys.argv[4])
    else:sys.exit("bad arguments")
