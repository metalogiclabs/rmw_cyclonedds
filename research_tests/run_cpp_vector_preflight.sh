#!/usr/bin/env bash
set -euo pipefail
git config --global --add safe.directory /source
src=/source/rmw_cyclonedds_cpp/src
head_root=$(find /opt/ros/jazzy/include -path '*/dds/ddsrt/endian.h' -print -quit)
test -n "$head_root"
include_dir=$(dirname "$(dirname "$(dirname "$head_root")")")
printf "source=%s\nheader=%s\ninclude_dir=%s\n" "$src" "$head_root" "$include_dir" > /evidence/paths.txt
git -C /source rev-parse HEAD > /evidence/research-source-commit.txt
git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/serdes.hpp > /evidence/serdes-source-blob.txt

for arm in baseline guarded; do
  mkdir -p "/tmp/$arm"
  cp -a "$src/." "/tmp/$arm/"
done
python3 - <<'PY'
from pathlib import Path
p=Path("/tmp/guarded/serdes.hpp")
s=p.read_text()
old="""  template<class T>
  inline void deserialize(std::vector<T> & x)
  {
    const uint32_t sz = deserialize_len(1);
    x.resize(sz);
    deserializeA(x.data(), sz);
  }"""
new="""  template<class T>
  inline void deserialize(std::vector<T> & x)
  {
    // This is an experiment, not an upstream fix.
    // Arithmetic types require sizeof(T) payload bytes each. A serialized
    // string requires at least its four-byte length field per element.
    const uint32_t min_elem_bytes =
      std::is_arithmetic<T>::value ? sizeof(T) :
      std::is_same<T, std::string>::value ? sizeof(uint32_t) : 1;
    const uint32_t sz = deserialize_len(min_elem_bytes);
    x.resize(sz);
    deserializeA(x.data(), sz);
  }"""
assert s.count(old)==1, "could not isolate exact original C++ vector branch"
s=s.replace(old,new)
s="#include <type_traits>\n"+s
p.write_text(s)
PY
diff -u /tmp/baseline/serdes.hpp /tmp/guarded/serdes.hpp > /evidence/candidate-guard.diff || test "$?" -eq 1
sha256sum /tmp/baseline/serdes.hpp /tmp/guarded/serdes.hpp > /evidence/header-sha256.txt

for arm in baseline guarded; do
  local_src="/tmp/$arm"
  g++ -std=c++17 -O0 -g -I"$local_src" -I"$include_dir" \
    /source/research_tests/cpp_vector_preflight.cpp \
    "$local_src/serdes.cpp" "$local_src/exception.cpp" \
    "$local_src/deserialization_exception.cpp" \
    -o "/evidence/probe-$arm" > "/evidence/build-$arm.log" 2>&1
  sha256sum "/evidence/probe-$arm" > "/evidence/probe-$arm.sha256"
  (
    ulimit -v 200000
    /evidence/probe-"$arm"
  ) > "/evidence/output-$arm.txt" 2> "/evidence/stderr-$arm.txt"
  printf '%s\n' "=== $arm ==="
  cat "/evidence/output-$arm.txt"
done
python3 - <<'PY'
import re
from pathlib import Path
def parse(arm):
  s=Path(f"/evidence/output-{arm}.txt").read_text()
  d={m.group(1):int(m.group(2)) for m in re.finditer(r'^(uint64|string) rejected=1 peak_requested=(\d+)',s,re.M)}
  assert len(d)==2,(arm,s)
  assert 'valid_uint64=1' in s,(arm,s)
  assert 'valid_string=1' in s,(arm,s)
  return d
a,b=parse("baseline"),parse("guarded")
print("baseline:",a,"guarded:",b)
for k in ("uint64","string"):
  assert a[k]>=8000, ("insufficient amplification in baseline",k,a[k])
  assert b[k]<1024, ("candidate did not reject before preallocation",k,b[k])
print("GATE PASS: native baseline preallocates before failing; experimental guard preflights")
PY
