#!/usr/bin/env bash
# Rebuild the exact clean upstream-facing Kilted patch with tests enabled.
# This is a qualification harness only; it does not alter the source-only PR.
set -euo pipefail

git config --global --add safe.directory /source
git config --global --add safe.directory /source/.git
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git g++ cmake ninja-build python3-colcon-common-extensions \
  ros-kilted-rclpy ros-kilted-test-msgs ros-kilted-rmw-cyclonedds-cpp \
  ros-kilted-ament-lint-auto ros-kilted-ament-lint-common
set +u
source /opt/ros/kilted/setup.bash
set -u

dpkg-query -W ros-kilted-rclpy ros-kilted-test-msgs \
  ros-kilted-rmw-cyclonedds-cpp ros-kilted-ament-lint-auto \
  > /evidence/kilted-packages.txt

UPSTREAM_KILTED=2c56f9b3feb3ed1e359a7ea852f2c7331ad41992
SOURCE_COMMIT=6234fd72b900a3a04e0917e0c6202ccc2d743818
SOURCE_BLOB=caaab0623f9c214ad7922fe1b71cd691bdd413f3
HEADER_PR=73c2fb62b2be3b752b098f44cc6c41b9c4bbe85a
SOURCE_PATH=rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp

git clone -q -b contrib/kilted-c-sequence-lifetime-20261104 \
  https://github.com/metalogiclabs/rmw_cyclonedds /tmp/rmw-kilted-lifetime
git -C /tmp/rmw-kilted-lifetime checkout -q --detach "$SOURCE_COMMIT"
test "$(git -C /tmp/rmw-kilted-lifetime rev-parse HEAD^1)" = "$UPSTREAM_KILTED"
test "$(git -C /tmp/rmw-kilted-lifetime rev-parse HEAD:"$SOURCE_PATH")" = "$SOURCE_BLOB"
test "$(git -C /tmp/rmw-kilted-lifetime diff --name-only "$UPSTREAM_KILTED" "$SOURCE_COMMIT")" = "$SOURCE_PATH"
git -C /tmp/rmw-kilted-lifetime show --format= --stat HEAD > /evidence/kilted-source-stat.txt
git -C /tmp/rmw-kilted-lifetime diff "$UPSTREAM_KILTED" "$SOURCE_COMMIT" \
  -- "$SOURCE_PATH" > /evidence/kilted-lifetime-only.patch
git -C /tmp/rmw-kilted-lifetime fetch -q \
  https://github.com/ros2/rmw_cyclonedds pull/625/head
test "$(git -C /tmp/rmw-kilted-lifetime rev-parse FETCH_HEAD)" = "$HEADER_PR"
git -C /tmp/rmw-kilted-lifetime show --format= FETCH_HEAD \
  -- rmw_cyclonedds_cpp/src/serdes.cpp > /evidence/kilted-pr625-header.patch
git -C /tmp/rmw-kilted-lifetime apply --check /evidence/kilted-pr625-header.patch
git -C /tmp/rmw-kilted-lifetime apply /evidence/kilted-pr625-header.patch
git -C /tmp/rmw-kilted-lifetime diff --check

colcon --log-base /tmp/kilted-logs build --merge-install \
  --base-paths /tmp/rmw-kilted-lifetime/rmw_cyclonedds_cpp \
  --packages-select rmw_cyclonedds_cpp \
  --build-base /tmp/kilted-build --install-base /tmp/kilted-install \
  --event-handlers console_cohesion+ --cmake-args -DBUILD_TESTING=ON \
  > /evidence/kilted-build.log 2>&1 || {
    tail -n 100 /evidence/kilted-build.log
    exit 1
  }

colcon --log-base /tmp/kilted-test-logs test \
  --packages-select rmw_cyclonedds_cpp --build-base /tmp/kilted-build \
  --install-base /tmp/kilted-install --event-handlers console_cohesion+ \
  > /evidence/kilted-test.log 2>&1 || {
    tail -n 100 /evidence/kilted-test.log
    exit 1
  }
colcon test-result --test-result-base /tmp/kilted-build --verbose \
  > /evidence/kilted-test-result.txt 2>&1 || {
    tail -n 100 /evidence/kilted-test-result.txt
    exit 1
  }
tail -n 15 /evidence/kilted-test-result.txt

test -f /tmp/kilted-install/lib/librmw_cyclonedds_cpp.so
sha256sum /tmp/kilted-install/lib/librmw_cyclonedds_cpp.so \
  > /evidence/kilted-library.sha256
export EXPECTED_LIB_DIR=/tmp/kilted-install/lib
export LD_LIBRARY_PATH="$EXPECTED_LIB_DIR:$LD_LIBRARY_PATH"
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
python3 /source/research_tests/jazzy_c_sequence_leak.py \
  --arm kilted --count 20000 > /evidence/kilted-sequence-output.txt 2>&1 || {
    tail -n 100 /evidence/kilted-sequence-output.txt
    exit 1
  }
tail -n 8 /evidence/kilted-sequence-output.txt
python3 /source/research_tests/jazzy_c_sequence_protected.py \
  --arm kilted --skip-count > /evidence/kilted-protected-output.txt 2>&1 || {
    tail -n 100 /evidence/kilted-protected-output.txt
    exit 1
  }
tail -n 5 /evidence/kilted-protected-output.txt
