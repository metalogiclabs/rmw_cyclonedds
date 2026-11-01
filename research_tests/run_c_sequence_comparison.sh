#!/usr/bin/env bash
# Independent source-pinned ROS Jazzy C allocation preflight comparison.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git cmake ninja-build g++ python3-colcon-common-extensions \
  ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-rmw-fastrtps-cpp ros-jazzy-test-msgs
set +u
source /opt/ros/jazzy/setup.bash
set -u
dpkg-query -W ros-jazzy-rmw-cyclonedds-cpp ros-jazzy-test-msgs ros-jazzy-rclpy \
  > /evidence/package-versions.txt

BASE_SHA="20b192ae744f2fe56767e68081a46ad0d7f7a0ec"
CANDIDATE_SHA="bfa40e6e09344b8ddda622956195f3132191d8b2"
PR625_SHA="73c2fb62b2be3b752b098f44cc6c41b9c4bbe85a"
git clone -q https://github.com/metalogiclabs/rmw_cyclonedds.git /tmp/cyclone-base
git -C /tmp/cyclone-base fetch -q https://github.com/ros2/rmw_cyclonedds.git pull/625/head
test "$(git -C /tmp/cyclone-base rev-parse FETCH_HEAD)" = "$PR625_SHA"
git -C /tmp/cyclone-base show --format= FETCH_HEAD -- \
  rmw_cyclonedds_cpp/src/serdes.cpp > /evidence/pr625.patch
test -s /evidence/pr625.patch
sha256sum /evidence/pr625.patch > /evidence/pr625-patch.sha256

for arm in baseline candidate; do
  src="/tmp/cyclone-$arm"
  if [[ "$arm" == "baseline" ]]; then
    src=/tmp/cyclone-base
    sha="$BASE_SHA"
  else
    git clone -q https://github.com/metalogiclabs/rmw_cyclonedds.git "$src"
    sha="$CANDIDATE_SHA"
  fi
  git -C "$src" checkout -q --detach "$sha"
  test "$(git -C "$src" rev-parse HEAD)" = "$sha"
  git -C "$src" apply --check /evidence/pr625.patch
  git -C "$src" apply /evidence/pr625.patch
  git -C "$src" diff --check
  printf '%s\n' "$sha" > "/evidence/$arm-source-sha.txt"
  colcon --log-base "/tmp/cyclone-logs-$arm" build \
    --merge-install --base-paths "$src/rmw_cyclonedds_cpp" \
    --packages-select rmw_cyclonedds_cpp \
    --build-base "/tmp/cyclone-build-$arm" \
    --install-base "/tmp/cyclone-install-$arm" \
    --event-handlers console_cohesion+ \
    --cmake-args -DBUILD_TESTING=OFF \
    > "/evidence/$arm-build.log" 2>&1
  test -f "/tmp/cyclone-install-$arm/lib/librmw_cyclonedds_cpp.so"
  sha256sum "/tmp/cyclone-install-$arm/lib/librmw_cyclonedds_cpp.so" \
    > "/evidence/$arm-library.sha256"
done

original_libs="$LD_LIBRARY_PATH"
for arm in baseline candidate; do
  export ARM="$arm"
  export EXPECTED_LIB_DIR="/tmp/cyclone-install-$arm/lib"
  export LD_LIBRARY_PATH="$EXPECTED_LIB_DIR:$original_libs"
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  ulimit -t 30
  /usr/bin/python3 /source/research_tests/c_sequence_memory_probe.py \
    > "/evidence/$arm-c-sequence.json" 2> "/evidence/$arm-c-sequence.stderr"
  cat "/evidence/$arm-c-sequence.json"
done
/usr/bin/python3 /source/research_tests/check_c_sequence_memory.py \
  > /evidence/c-sequence-verdict.txt
cat /evidence/c-sequence-verdict.txt
