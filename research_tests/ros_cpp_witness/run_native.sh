#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git g++ cmake python3-colcon-common-extensions \
  ros-jazzy-rclcpp ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp
set +u
source /opt/ros/jazzy/setup.bash
set -u
dpkg-query -W ros-jazzy-rclcpp ros-jazzy-test-msgs \
  ros-jazzy-rmw-cyclonedds-cpp > /evidence/packages.txt
BASE=20b192ae744f2fe56767e68081a46ad0d7f7a0ec
CANDIDATE=bbf8c1ad0b2f672f5e95c9ad17ba86cbaee6a2bf
src=/tmp/cyclone
git clone --quiet --branch jazzy https://github.com/ros2/rmw_cyclonedds.git "$src"
test "$(git -C "$src" rev-parse HEAD)" = "$BASE"
git -C "$src" fetch -q https://github.com/metalogiclabs/rmw_cyclonedds.git "$CANDIDATE"
test "$(git -C "$src" rev-parse FETCH_HEAD)" = "$CANDIDATE"
test "$(git -C "$src" rev-parse FETCH_HEAD^)" = "$BASE"
git -C "$src" show --format= "$CANDIDATE" -- rmw_cyclonedds_cpp/src/serdes.hpp rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp > /evidence/combined-fix.patch
test -s /evidence/combined-fix.patch
sha256sum /evidence/combined-fix.patch > /evidence/patch.sha256

colcon --log-base /tmp/probe-logs build \
  --base-paths /source/research_tests/ros_cpp_witness \
  --packages-select mathgraph_cyclone_cpp_witness \
  --build-base /tmp/probe-build \
  --install-base /tmp/probe-install \
  --event-handlers console_cohesion+ \
  --cmake-args -DBUILD_TESTING=OFF > /evidence/cpp-probe-build.log 2>&1
app=/tmp/probe-install/mathgraph_cyclone_cpp_witness/lib/mathgraph_cyclone_cpp_witness/ros_cpp_real_path
test -x "$app"
sha256sum "$app" > /evidence/cpp-probe-binary.sha256

build_rmw() {
 local arm="$1"
 colcon --log-base "/tmp/cyclone-logs-$arm" build --merge-install \
   --base-paths "$src/rmw_cyclonedds_cpp" \
   --packages-select rmw_cyclonedds_cpp \
   --build-base "/tmp/cyclone-build-$arm" \
   --install-base "/tmp/cyclone-install-$arm" \
   --event-handlers console_cohesion+ \
   --cmake-args -DBUILD_TESTING=OFF > "/evidence/$arm-build.log" 2>&1
 sha256sum "/tmp/cyclone-install-$arm/lib/librmw_cyclonedds_cpp.so" > "/evidence/$arm-library.sha256"
}
build_rmw baseline
git -C "$src" checkout -q --detach "$CANDIDATE"
test "$(git -C "$src" rev-parse HEAD:rmw_cyclonedds_cpp/src/serdes.hpp)" = 8dbd4aafa8e143ad4e02bc3e83f018131822cfb3
test "$(git -C "$src" rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp)" = 86e882abb71f31c08e58dcf7365d3707030f4364
build_rmw patched
ROS_PATH="$LD_LIBRARY_PATH"
for arm in baseline patched; do
 (
   export LD_LIBRARY_PATH="/tmp/cyclone-install-$arm/lib:$ROS_PATH"
   export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
   ulimit -v 260000
   "$app"
 ) > "/evidence/$arm-output.txt" 2> "/evidence/$arm-stderr.txt"
 cat "/evidence/$arm-output.txt"
done
python3 - <<'PY'
from pathlib import Path
import re
summary={}
for arm in ("baseline","patched"):
  t=Path(f"/evidence/{arm}-output.txt").read_text()
  assert "valid_roundtrip=1" in t,(arm,t)
  assert "truncated_uint64 rejected=1" in t,(arm,t)
  assert "cyclone_loaded=1" in t,(arm,t)
  m=re.search(r"max_alloc_request=(\d+)",t)
  assert m,(arm,t)
  p=re.search(r"rmw_library=([^\n]+)",t)
  assert p and f"cyclone-install-{arm}/lib" in p.group(1),(arm,t)
  summary[arm]=int(m.group(1))
print("C++ public serialization differential", summary)
assert summary["baseline"] >= 65536, "UNKNOWN: baseline did not expose C++ vector allocation"
assert summary["patched"] < 2048, "REJECT: candidate still allocated oversized vector"
print("GATE PASS: public C++ serialization path; source-only guard; valid control preserved")
Path("/evidence/conclusion.txt").write_text(str(summary))
PY
