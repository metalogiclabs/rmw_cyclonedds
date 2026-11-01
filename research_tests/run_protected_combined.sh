#!/usr/bin/env bash
# Protected native, source-identical combined C/C++ preflight comparison.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git cmake ninja-build g++ curl python3-colcon-common-extensions \
  ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-rmw-fastrtps-cpp ros-jazzy-test-msgs
set +u
source /opt/ros/jazzy/setup.bash
set -u
dpkg-query -W ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-rmw-fastrtps-cpp ros-jazzy-rclpy ros-jazzy-test-msgs \
 > /evidence/packages.txt
BASE=20b192ae744f2fe56767e68081a46ad0d7f7a0ec
COMBINED=bbf8c1ad0b2f672f5e95c9ad17ba86cbaee6a2bf
PR625=73c2fb62b2be3b752b098f44cc6c41b9c4bbe85a
# Verify immutable blobs, not a friendly branch label.
test "$(git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/serdes.hpp)" = 8dbd4aafa8e143ad4e02bc3e83f018131822cfb3
test "$(git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp)" = 86e882abb71f31c08e58dcf7365d3707030f4364
git clone --quiet -b jazzy https://github.com/metalogiclabs/rmw_cyclonedds.git /tmp/arm-base
git -C /tmp/arm-base checkout --quiet --detach "$BASE"
git clone --quiet https://github.com/metalogiclabs/rmw_cyclonedds.git /tmp/arm-candidate
git -C /tmp/arm-candidate checkout --quiet --detach "$COMBINED"
git -C /tmp/arm-base fetch --quiet https://github.com/ros2/rmw_cyclonedds.git pull/625/head
test "$(git -C /tmp/arm-base rev-parse FETCH_HEAD)" = "$PR625"
git -C /tmp/arm-base show --format= FETCH_HEAD -- rmw_cyclonedds_cpp/src/serdes.cpp > /evidence/pr625.patch
test -s /evidence/pr625.patch
sha256sum /evidence/pr625.patch > /evidence/pr625.sha256
curl -fsSL --retry 3 https://raw.githubusercontent.com/heathsanchez/test/dcbd06ffa3e1dfef1191767164c676f4f7984815/research/ros-fastrtps-cdr-20261101/probe.py -o /tmp/cdr-probe.py
test "$(git hash-object /tmp/cdr-probe.py)" = e641b77cebf5ad6ced96111bf4529d359a5a5718
printf '%s\n' "dcbd06ffa3e1dfef1191767164c676f4f7984815" > /evidence/probe-source-ref.txt
# Source-native control includes PR625 in *both* arms, explicitly isolating
# our 2-file sequence preflight from the existing upstream short-header fix.
for arm in base candidate; do
  src="/tmp/arm-$arm"
  git -C "$src" apply --check /evidence/pr625.patch
  git -C "$src" apply /evidence/pr625.patch
  git -C "$src" diff --check
  git -C "$src" rev-parse HEAD > "/evidence/$arm-source-sha.txt"
  colcon --log-base "/tmp/logs-$arm" build \
    --merge-install --base-paths "$src/rmw_cyclonedds_cpp" \
    --packages-select rmw_cyclonedds_cpp \
    --build-base "/tmp/build-$arm" --install-base "/tmp/install-$arm" \
    --event-handlers console_cohesion+ \
    --cmake-args -DBUILD_TESTING=OFF > "/evidence/$arm-build.log" 2>&1
  sha256sum "/tmp/install-$arm/lib/librmw_cyclonedds_cpp.so" > "/evidence/$arm-library.sha256"
done
original_libs="$LD_LIBRARY_PATH"
for arm in base candidate; do
  export LD_LIBRARY_PATH="/tmp/install-$arm/lib:$original_libs"
  export EXPECTED_LIB_DIR="/tmp/install-$arm/lib"
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  /usr/bin/python3 - <<'PY' > "/evidence/$arm-maps.txt"
import os
from test_msgs.msg import Arrays
from rclpy.serialization import deserialize_message, serialize_message
assert isinstance(deserialize_message(serialize_message(Arrays()), Arrays), Arrays)
paths=sorted({line.split()[-1] for line in open("/proc/self/maps") if "/librmw_cyclonedds_cpp.so" in line and "/" in line})
print("\n".join(paths))
assert paths and all(p.startswith(os.environ["EXPECTED_LIB_DIR"]) for p in paths), paths
PY
  /usr/bin/python3 /tmp/cdr-probe.py > "/evidence/$arm-matrix.jsonl" 2> "/evidence/$arm-matrix.stderr"
  cp /evidence/results.json "/evidence/$arm-results.json"
  /usr/bin/python3 /source/research_tests/combined_native_smoke.py \
    > "/evidence/$arm-bounded.json" 2> "/evidence/$arm-bounded.stderr"
done
/usr/bin/python3 /source/research_tests/check_protected_combined.py | tee /evidence/verdict.txt
