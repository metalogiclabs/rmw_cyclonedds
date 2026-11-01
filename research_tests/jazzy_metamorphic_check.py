#!/usr/bin/env python3
"""Compare only meaningful behavior for the two source-pinned ROS arms."""
import collections,json
def get(arm):
    rows=json.load(open("/evidence/"+arm+"-metamorphic.json"))
    assert len(rows)==359,(arm,len(rows))
    return {r["index"]:r for r in rows}
b,c=get("base"),get("candidate")
assert set(b)==set(c)
changes=[]
for i in b:
    before,after=b[i],c[i]
    ident=("family","count","variant")
    assert all(before[key]==after[key] for key in ident),(before,after)
    assert after["outcome"] in ("accepted","error"),after
    if after["variant"]=="valid":
        assert before["outcome"]==after["outcome"]=="accepted",(before,after)
    if after["variant"] in ("cut_1","large_count"):
        assert before["outcome"]==after["outcome"]=="error",(before,after)
    if before["outcome"]!=after["outcome"]:
        changes.append({"index":i,"family":after["family"],"count":after["count"],
                        "variant":after["variant"],"before":before["outcome"],"after":after["outcome"]})
counts={}
for name,data in (("base",b),("candidate",c)):
    counts[name]=dict(collections.Counter(r["outcome"] for r in data.values()))
print(json.dumps({"total_per_arm":len(b),"counts":counts,"changes":changes},sort_keys=True))
json.dump({"counts":counts,"changes":changes},open("/evidence/differential.json","w"),indent=2)
# Reject any formerly accepted prefix that the candidate rejects until reviewed:
# the corrupted input may be legitimate if only optional padding was removed.
assert not changes,changes
print("GATE PASS: 718 source-native executions, valid controls preserved, malformed hard controls rejected; no process signals or timeouts")
