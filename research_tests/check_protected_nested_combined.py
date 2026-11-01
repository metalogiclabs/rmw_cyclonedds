#!/usr/bin/env python3
"""Fail-closed verification of protected Jazzy comparison of combined preflight."""
import collections, json
def load(arm):
    with open(f"/evidence/{arm}-results.json") as f:
        rows=json.load(f)["cases"]
    assert len(rows)==224,(arm,len(rows))
    return {(r["backend"],r["type"],r["case"]):r for r in rows}
b,p=load("base"),load("candidate")
assert set(b)==set(p)
short=("empty","header_1","header_2","header_3")
for arm,rows in (("base",b),("candidate",p)):
    valid=[(k,r) for k,r in rows.items() if k[2]=="valid"]
    assert len(valid)==14
    for k,r in valid:
        assert r["outcome"]=="accepted",(arm,k,r)
    shorts=[(k,r) for k,r in rows.items() if k[0]=="rmw_cyclonedds_cpp" and k[2] in short]
    assert len(shorts)==28 and all(r["outcome"]=="error" for k,r in shorts),(arm,shorts)
    cycl=[(k,r) for k,r in rows.items() if k[0]=="rmw_cyclonedds_cpp"]
    bad=[(k,r) for k,r in cycl if r["outcome"] in ("signal","timeout","process_error","invalid_record")]
    assert not bad,(arm,bad)
    print(arm,"cyclone",dict(collections.Counter(r["outcome"] for k,r in cycl)))
    print(arm,"fastdds",dict(collections.Counter(r["outcome"] for k,r in rows.items() if k[0]=="rmw_fastrtps_cpp")))
deltas=[{"key":k,"before":b[k]["outcome"],"after":p[k]["outcome"]}
        for k in sorted(b) if b[k]["outcome"]!=p[k]["outcome"]]
cycl_deltas=[d for d in deltas if d["key"][0]=="rmw_cyclonedds_cpp"]
assert not cycl_deltas,cycl_deltas
print("all-deltas",json.dumps(deltas))
with open("/evidence/comparison.json","w") as f: json.dump({"deltas":deltas},f,indent=2)
a=json.load(open("/evidence/base-bounded.json"))
z=json.load(open("/evidence/candidate-bounded.json"))
assert a["malformed_outcome"]=="RMWError" and z["malformed_outcome"]=="RMWError",(a,z)
assert "unable initialize generic sequence" in a["malformed_error"],a
assert "invalid data size" in z["malformed_error"],z
assert a["declared_float64_count"]==z["declared_float64_count"]==1048576
assert a["input_size"]==z["input_size"]==1048600
assert all(path.startswith("/tmp/install-base/lib") for path in a["loaded_libs"]),a
assert all(path.startswith("/tmp/install-candidate/lib") for path in z["loaded_libs"]),z
print("bounded-c-sequence",json.dumps({"baseline_error":a["malformed_error"],"candidate_error":z["malformed_error"]}))
print("GATE PASS: source-pinned combined candidate preserves all native positive controls,")
print("  all 28 PR625 short-header controls, and all 112 Cyclone outcomes;")
print("  malformed C sequence fails via input-size preflight instead of attempted allocation.")
