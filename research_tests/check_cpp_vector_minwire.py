#!/usr/bin/env python3
import json
import re
from pathlib import Path

def parse(path):
    text = Path(path).read_text()
    found = {}
    for key in ["bad_uint64", "bad_string"]:
        match = re.search(rf"^{key} refused=(\d+) max_new=(\d+) bytes=(\d+)$", text, re.M)
        assert match is not None, (path,key,text)
        found[key] = {"refused":int(match[1]), "peak_request":int(match[2]), "input_bytes":int(match[3])}
    for key in ["valid_uint64", "valid_string", "valid_chars"]:
        assert re.search(rf"^{key}=1$",text,re.M), (path,key,text)
    return found

base=parse("/evidence/baseline.txt")
fix=parse("/evidence/patched.txt")
for key,old_floor in [("bad_uint64",256),("bad_string",1024)]:
    assert base[key]["refused"]==1 and fix[key]["refused"]==1
    assert base[key]["peak_request"]>=old_floor, (key,base[key])
    assert fix[key]["peak_request"] < old_floor, (key,fix[key])
    assert fix[key]["input_bytes"]==base[key]["input_bytes"]==40
print(json.dumps({"baseline":base,"patched":fix,"gate":"PASS; preflight avoids oversize allocation in scoped C++ vector paths; valid controls preserved"},indent=2))
Path("/evidence/comparison.json").write_text(json.dumps({"baseline":base,"patched":fix},indent=2))
