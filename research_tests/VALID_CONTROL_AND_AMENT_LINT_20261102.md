# Jazzy valid-message and repository-lint verification (2026-11-02 NZDT)

**Scope:** Native checks of the proposed two-header CDR sequence preflight,
performed on the public research branch. This is not an upstream change request
and does not establish the safety of all malformed inputs.

## Exact source under test

- `rmw_cyclonedds_cpp/src/TypeSupport_impl.hpp` Git blob:
  `9556cd8e3a6c38a1669fbcfed1ec5a3325c874e2`
- `rmw_cyclonedds_cpp/src/serdes.hpp` Git blob:
  `b3be1fcb5385a97f37f8003a6f642f8f23d38716`
- Native environment: `ros:jazzy-ros-base` Docker container,
  `ros-jazzy-rmw-cyclonedds-cpp` packaged baseline and a newly compiled
  `rmw_cyclonedds_cpp` candidate. Both shared libraries were fingerprinted.

## Legal zero-field nested message sequence

[Actions run 41354000076](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41354000076)
(commit `091a990ae5d4e18a3db50af346be1fa75cd50419`):

| Native library | Serialized bytes | Elements decoded | Result |
| --- | ---: | ---: | --- |
| Packaged Jazzy baseline | 580 | 256/256 | PASS |
| Source-built candidate | 580 | 256/256 | PASS |

The test constructs and round-trips a valid
`test_msgs/UnboundedSequences` with 256 `Constants` elements.
Independent processes verified the loaded library paths in `/proc/self/maps`.
The suspected zero-field nested-sequence compatibility regression was **not
reproduced** by this control. No general claim about other message layouts follows.

Artifact `13102336794`; archive digest
`sha256:92c5602ea21bb75c44868fdc2c9728d5e7a6b716e381c767702b89d4de5f8f55`.

## Repository-native ament checks

[Actions run 41354535319](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41354535319)
(commit `8736259ad7790ff7af70f41fd6b5fb9c119d65af`):

- Built `rmw_cyclonedds_cpp` natively with `BUILD_TESTING=ON`.
- 6/6 registered lint tests passed: copyright, cppcheck, cpplint,
  lint_cmake, uncrustify, xmllint.
- `AMENT_CPPCHECK_ALLOW_SLOW_VERSIONS=1` enabled the actual cppcheck run;
  the default distro guard would otherwise skip that analyzer.
- `cppcheck` explicitly reported `No problems found`.
- Docker resource limits: 2 GiB memory/swap, no core dumps.

Artifact `13102174278`; archive digest
`sha256:10c3a9a2b67c3f8e497746476bf05ba68555a2c877d308273408584e3de05522`.

Initial lint runs `41354120536`, `41354238549`, and `41354316181`
failed due to CI wrapper configuration (merged install setting and overly
broad `colcon` package discovery), **before the lint suite could execute**.
Their logs remain available and are not classified as source-code failures.

## Submission-readiness limitations

- This research does not substitute for ROS tier-1 platform CI, maintainer
  peer review, or a signed contributor-origin declaration.
- The two source commits on the proposed Kilted change branch do **not** yet
  carry `Signed-off-by:` trailers required by the package's DCO policy.
- The separate high-memory-consumption report remains **UNKNOWN**; neither
  this valid-message check nor lint establishes its root cause.
- Follow the package's REP-2006 coordinated disclosure policy if a new
  security-relevant issue is confirmed. No new vulnerability details are
  asserted in this report.

References: [QUALITY_DECLARATION.md](../rmw_cyclonedds_cpp/QUALITY_DECLARATION.md),
[CONTRIBUTING.md](../CONTRIBUTING.md).
