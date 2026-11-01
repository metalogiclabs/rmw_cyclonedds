#!/usr/bin/env bash
# Compare both native RMW libraries on the same bounded C++ deserialization path.
set -euo pipefail
git config --global --add safe.directory /source
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git g++ cmake ninja-build python3-colcon-common-extensions \
  ros-jazzy-rclcpp ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp
set +u
source /opt/ros/jazzy/setup.bash
set -u
dpkg-query -W ros-jazzy-rclcpp ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp > /evidence/packages.txt

BASE=20b192ae744f2fe56767e68081a46ad0d7f7a0ec
CANDIDATE=fddab142fbef448ed6b2ceeaf4c1e9b1d95bae6d
PR625=73c2fb62b2be3b752b098f44cc6c41b9c4bbe85a
test "$(git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp)" = 9556cd8e3a6c38a1669fbcfed1ec5a3325c874e2
test "$(git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/serdes.hpp)" = b3be1fcb5385a97f37f8003a6f642f8f23d38716
sha256sum /source/research_tests/jazzy_allocator_residency.cpp /source/research_tests/jazzy_allocator_residency_check.py > /evidence/harness.sha256

git clone -q -b jazzy https://github.com/metalogiclabs/rmw_cyclonedds /tmp/rmw-base
git -C /tmp/rmw-base checkout -q --detach "$BASE"
git clone -q https://github.com/metalogiclabs/rmw_cyclonedds /tmp/rmw-candidate
git -C /tmp/rmw-candidate checkout -q --detach "$CANDIDATE"
git -C /tmp/rmw-base fetch -q https://github.com/ros2/rmw_cyclonedds pull/625/head
test "$(git -C /tmp/rmw-base rev-parse FETCH_HEAD)" = "$PR625"
git -C /tmp/rmw-base show --format= FETCH_HEAD -- rmw_cyclonedds_cpp/src/serdes.cpp > /evidence/pr625.patch
test -s /evidence/pr625.patch
sha256sum /evidence/pr625.patch > /evidence/pr625.sha256

for arm in base candidate; do
  src="/tmp/rmw-$arm"
  git -C "$src" apply --check /evidence/pr625.patch
  git -C "$src" apply /evidence/pr625.patch
  git -C "$src" diff --check
  git -C "$src" rev-parse HEAD > "/evidence/$arm-head.txt"
  git -C "$src" rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp > "/evidence/$arm-typesupport-blob.txt"
  git -C "$src" rev-parse HEAD:rmw_cyclonedds_cpp/src/serdes.hpp > "/evidence/$arm-serdes-blob.txt"
  colcon --log-base "/tmp/logs-$arm" build --merge-install \
    --base-paths "$src/rmw_cyclonedds_cpp" --packages-select rmw_cyclonedds_cpp \
    --build-base "/tmp/build-$arm" --install-base "/tmp/install-$arm" \
    --event-handlers console_cohesion+ --cmake-args -DBUILD_TESTING=OFF \
    > "/evidence/$arm-build.log" 2>&1
  test -f "/tmp/install-$arm/lib/librmw_cyclonedds_cpp.so"
  sha256sum "/tmp/install-$arm/lib/librmw_cyclonedds_cpp.so" > "/evidence/$arm-library.sha256"
done

colcon --log-base /tmp/probe-logs build \
  --base-paths /source/research_tests/allocator_residency_witness \
  --packages-select mathgraph_cyclone_allocator_residency \
  --build-base /tmp/probe-build --install-base /tmp/probe-install \
  --event-handlers console_cohesion+ --cmake-args -DBUILD_TESTING=OFF \
  > /evidence/probe-build.log 2>&1
app=/tmp/probe-install/mathgraph_cyclone_allocator_residency/lib/mathgraph_cyclone_allocator_residency/cyclone_allocator_residency
test -x "$app"
sha256sum "$app" > /evidence/probe-binary.sha256

ros_libraries="$LD_LIBRARY_PATH"
for arm in base candidate; do
  export EXPECTED_LIB_DIR="/tmp/install-$arm/lib"
  export LD_LIBRARY_PATH="$EXPECTED_LIB_DIR:$ros_libraries"
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  for mode_count in valid:8 malformed:8192 malformed:65536 malformed:262144; do
    mode="${mode_count%%:*}"
    count="${mode_count##*:}"
    for repeat in 0 1 2 3 4; do
      (
        ulimit -v 360000
        ulimit -t 5
        ulimit -c 0
        timeout 10s "$app" "$mode" "$count"
      ) > "/evidence/$arm-$mode-$count-$repeat.txt" \
        2> "/evidence/$arm-$mode-$count-$repeat.stderr"
    done
  done
done
/usr/bin/python3 /source/research_tests/jazzy_allocator_residency_check.py > /evidence/verdict.json
cat /evidence/verdict.json
