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
JAZZY_BASE=20b192ae744f2fe56767e68081a46ad0d7f7a0ec
JAZZY_BASE_TYPESUPPORT=736e08846a9aebb2983014e9ef2f7a6fdbc61b75
git -C /source merge-base --is-ancestor "$BASE629" HEAD
git -C /source rev-parse HEAD > /evidence/runner-commit.txt
git -C /source rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp \
  > /evidence/source-typesupport-blob.txt
sha256sum /source/research_tests/jazzy_c_sequence_leak.py \
  /source/research_tests/jazzy_c_sequence_protected.py \
  /source/research_tests/c-sequence-lifetime-only.patch \
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

ROS_LIBRARIES="$LD_LIBRARY_PATH"
export EXPECTED_LIB_DIR=/tmp/lifetime-install/lib
export LD_LIBRARY_PATH="$EXPECTED_LIB_DIR:$ROS_LIBRARIES"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
python3 /source/research_tests/jazzy_c_sequence_leak.py --arm source --count 20000 \
  > /evidence/sequence-output.txt 2>&1 || {
    tail -n 30 /evidence/sequence-output.txt
    exit 1
  }
tail -n 30 /evidence/sequence-output.txt
python3 /source/research_tests/jazzy_c_sequence_protected.py --arm source \
  > /evidence/protected-output.txt 2>&1 || {
    tail -n 30 /evidence/protected-output.txt
    exit 1
  }
tail -n 5 /evidence/protected-output.txt

# An independent source-only arm: identical upstream Jazzy TypeSupport source
# to the Kilted target, with the lifetime patch but without PR #629 preflight.
git clone -q -b jazzy https://github.com/metalogiclabs/rmw_cyclonedds /tmp/rmw-standalone
git -C /tmp/rmw-standalone checkout -q --detach "$JAZZY_BASE"
test "$(git -C /tmp/rmw-standalone rev-parse HEAD:rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp)" = "$JAZZY_BASE_TYPESUPPORT"
git -C /tmp/rmw-standalone apply --check \
  /source/research_tests/c-sequence-lifetime-only.patch
git -C /tmp/rmw-standalone apply \
  /source/research_tests/c-sequence-lifetime-only.patch
git -C /tmp/rmw-standalone apply --check /evidence/pr625.patch
git -C /tmp/rmw-standalone apply /evidence/pr625.patch
git -C /tmp/rmw-standalone diff --check
git -C /tmp/rmw-standalone diff > /evidence/standalone-source.patch

colcon --log-base /tmp/standalone-logs build --merge-install \
  --base-paths /tmp/rmw-standalone/rmw_cyclonedds_cpp \
  --packages-select rmw_cyclonedds_cpp \
  --build-base /tmp/standalone-build --install-base /tmp/standalone-install \
  --event-handlers console_cohesion+ --cmake-args -DBUILD_TESTING=OFF \
  > /evidence/standalone-build.log 2>&1
test -f /tmp/standalone-install/lib/librmw_cyclonedds_cpp.so
sha256sum /tmp/standalone-install/lib/librmw_cyclonedds_cpp.so \
  > /evidence/standalone-library.sha256

export EXPECTED_LIB_DIR=/tmp/standalone-install/lib
export LD_LIBRARY_PATH="$EXPECTED_LIB_DIR:$ROS_LIBRARIES"
python3 /source/research_tests/jazzy_c_sequence_leak.py --arm standalone --count 20000 \
  > /evidence/standalone-sequence-output.txt 2>&1 || {
    tail -n 30 /evidence/standalone-sequence-output.txt
    exit 1
  }
tail -n 7 /evidence/standalone-sequence-output.txt
python3 /source/research_tests/jazzy_c_sequence_protected.py \
  --arm standalone --skip-count \
  > /evidence/standalone-protected-output.txt 2>&1 || {
    tail -n 30 /evidence/standalone-protected-output.txt
    exit 1
  }
tail -n 3 /evidence/standalone-protected-output.txt
