#!/usr/bin/env python3
import re, json
from pathlib import Path
pat=re.compile(r'^CASE n=(\d+) wire=(\d+) max_alloc=(\d+) max_valid_alloc=(\d+) rejected=(\d+) valid=(\d+) string_object_bytes=(\d+)$',re.M)
data={}
for arm in ("base","patched"):
    content=Path(f"/evidence/{arm}-result.txt").read_text()
    assert "BOUNDARY 1" in content,(arm,content)
    rows=[dict(zip(("n","wire","max_alloc","max_valid_alloc","rejected","valid","string_bytes"),map(int,m.groups()))) for m in pat.finditer(content)]
    assert [r["n"] for r in rows]==[256,2048,8192],(arm,rows)
    assert all(r["rejected"]==1 and r["valid"]==1 for r in rows),(arm,rows)
    assert all(r["max_alloc"]>=r["n"]*r["string_bytes"] for r in rows),(arm,rows)
    assert all(r["max_valid_alloc"]>=r["n"]*r["string_bytes"] for r in rows),(arm,rows)
    data[arm]=rows
assert [r["wire"] for r in data["base"]]==[r["wire"] for r in data["patched"]]
a,b=data["base"][-1],data["patched"][-1]
assert b["max_alloc"]/b["wire"]>=3.5,(a,b)
assert a["max_alloc"]/a["wire"]>=3.5,(a,b)
# A source-only preflight controls impossible sequence lengths but cannot
# bound representational expansion for plausible (but later-invalid) payloads.
summary={"arms":data,"largest_case":{"n":b["n"],"wire_bytes":b["wire"],
"max_allocation_base_bytes":a["max_alloc"],
"max_allocation_patched_bytes":b["max_alloc"],
"max_allocation_valid_base_bytes":a["max_valid_alloc"],
"max_allocation_valid_patched_bytes":b["max_valid_alloc"],
"patched_ratio":round(b["max_alloc"]/b["wire"],3)},
"verdict":"WARRANTED_BOUNDED: legitimate wire-to-heap expansion remains; not a new security vulnerability"}
Path("/evidence/comparison.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary["largest_case"],sort_keys=True))
print("GATE PASS: both valid and malformed decodes incur in-memory representation expansion;")
print("  this bounded test does not establish a distinct memory-safety vulnerability")
