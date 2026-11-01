#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git g++ cmake ninja-build python3-colcon-common-extensions \
  ros-jazzy-rclcpp ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp
set +u
source /opt/ros/jazzy/setup.bash
set -u
dpkg-query -W ros-jazzy-rclcpp ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp > /evidence/packages.txt
BASE=20b192ae744f2fe56767e68081a46ad0d7f7a0ec
PATCHED=fddab142fbef448ed6b2ceeaf4c1e9b1d95bae6d
src=/tmp/cyclone-src
git clone --quiet --branch jazzy https://github.com/ros2/rmw_cyclonedds.git "$src"
test "$(git -C "$src" rev-parse HEAD)" = "$BASE"
git -C "$src" fetch --quiet https://github.com/metalogiclabs/rmw_cyclonedds.git "$PATCHED"
test "$(git -C "$src" rev-parse FETCH_HEAD)" = "$PATCHED"
test "$(git -C "$src" rev-parse FETCH_HEAD^)" = "$BASE"
git -C "$src" show --format= "$PATCHED" -- rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp rmw_cyclonedds_cpp/src/serdes.hpp > /evidence/candidate.patch
test -s /evidence/candidate.patch
sha256sum /evidence/candidate.patch > /evidence/patch.sha256

colcon --log-base /tmp/witness-logs build \
  --base-paths /source/research_tests/amplification_witness \
  --packages-select mathgraph_cyclone_cpp_witness \
  --build-base /tmp/witness-build --install-base /tmp/witness-install \
  --cmake-args -DBUILD_TESTING=OFF > /evidence/witness-build.log 2>&1
app=/tmp/witness-install/mathgraph_cyclone_cpp_witness/lib/mathgraph_cyclone_cpp_witness/ros_cpp_real_path
test -x "$app"
sha256sum "$app" > /evidence/witness.sha256
build_arm() {
  local arm="$1"
  colcon --log-base "/tmp/rmw-logs-$arm" build --merge-install \
    --base-paths "$src/rmw_cyclonedds_cpp" --packages-select rmw_cyclonedds_cpp \
    --build-base "/tmp/rmw-build-$arm" --install-base "/tmp/rmw-install-$arm" \
    --cmake-args -DBUILD_TESTING=OFF > "/evidence/$arm-build.log" 2>&1
  sha256sum "/tmp/rmw-install-$arm/lib/librmw_cyclonedds_cpp.so" > "/evidence/$arm-lib.sha256"
}
build_arm base
git -C "$src" apply --check /evidence/candidate.patch
git -C "$src" apply /evidence/candidate.patch
git -C "$src" diff --check
build_arm patched
orig="$LD_LIBRARY_PATH"
for arm in base patched; do
  (
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export LD_LIBRARY_PATH="/tmp/rmw-install-$arm/lib:$orig"
    export EXPECTED_LIB_DIR="/tmp/rmw-install-$arm/lib"
    ulimit -v 260000
    "$app"
  ) > "/evidence/$arm-result.txt" 2> "/evidence/$arm-stderr.txt"
  cat "/evidence/$arm-result.txt"
done
/usr/bin/python3 /source/research_tests/check_amplification.py | tee /evidence/verdict.txt
