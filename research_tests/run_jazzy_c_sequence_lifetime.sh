#!/usr/bin/env bash
# Exercise a source-built Jazzy C introspection deserializer with fixed #625.
set -euo pipefail
git config --global --add safe.directory /source
git config --global --add safe.directory /source/.git
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git g++ cmake ninja-build python3-colcon-common-extensions \
  ros-jazzy-rclpy ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp
set +u
source /opt/ros/jazzy/setup.bash
set -u
dpkg-query -W ros-jazzy-rclpy ros-jazzy-test-msgs ros-jazzy-rmw-cyclonedds-cpp \
  > /evidence/packages.txt

PR625=73c2fb62b2be3b752b098f44cc6c41b9c4bbe85a
BASE629=96db6375b3b9b0c80481fa445f2d1f393e74c955
JAZZY629=fddab142fbef448ed6b2ceeaf4c1e9b1d95bae6d
JAZZY_TYPESUPPORT=9556cd8e3a6c38a1669fbcfed1ec5a3325c874e2
git -C /source merge-base --is-ancestor "$BASE629" HEAD
git -C /source rev-parse HEAD > /evidence/runner-commit.txt
git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp \
  > /evidence/source-typesupport-blob.txt
sha256sum /source/research_tests/jazzy_c_sequence_leak.py \
  /source/research_tests/run_jazzy_c_sequence_lifetime.sh \
  > /evidence/harness.sha256

git clone -q -b jazzy https://github.com/metalogiclabs/rmw_cyclonedds /tmp/rmw-lifetime
git -C /tmp/rmw-lifetime checkout -q --detach "$JAZZY629"
test "$(git -C /tmp/rmw-lifetime rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp)" = "$JAZZY_TYPESUPPORT"
test "$(git -C /source rev-parse "$BASE629":rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp)" = "$JAZZY_TYPESUPPORT"
cp /source/rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp \
  /tmp/rmw-lifetime/rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp
git -C /tmp/rmw-lifetime diff -- rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp \
  > /evidence/c-sequence-change.patch
git -C /tmp/rmw-lifetime fetch -q https://github.com/ros2/rmw_cyclonedds pull/625/head
test "$(git -C /tmp/rmw-lifetime rev-parse FETCH_HEAD)" = "$PR625"
git -C /tmp/rmw-lifetime show --format= FETCH_HEAD -- rmw_cyclonedds_cpp/src/serdes.cpp \
  > /evidence/pr625.patch
test -s /evidence/pr625.patch
git -C /tmp/rmw-lifetime apply --check /evidence/pr625.patch
git -C /tmp/rmw-lifetime apply /evidence/pr625.patch
git -C /tmp/rmw-lifetime diff --check

colcon --log-base /tmp/lifetime-logs build --merge-install \
  --base-paths /tmp/rmw-lifetime/rmw_cyclonedds_cpp \
  --packages-select rmw_cyclonedds_cpp \
  --build-base /tmp/lifetime-build --install-base /tmp/lifetime-install \
  --event-handlers console_cohesion+ --cmake-args -DBUILD_TESTING=OFF \
  > /evidence/build.log 2>&1
test -f /tmp/lifetime-install/lib/librmw_cyclonedds_cpp.so
sha256sum /tmp/lifetime-install/lib/librmw_cyclonedds_cpp.so \
  > /evidence/library.sha256

export EXPECTED_LIB_DIR=/tmp/lifetime-install/lib
export LD_LIBRARY_PATH="$EXPECTED_LIB_DIR:$LD_LIBRARY_PATH"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
python3 /source/research_tests/jazzy_c_sequence_leak.py --arm source --count 20000 \
  > /evidence/sequence-output.txt 2>&1 || {
    tail -n 30 /evidence/sequence-output.txt
    exit 1
  }
tail -n 30 /evidence/sequence-output.txt
