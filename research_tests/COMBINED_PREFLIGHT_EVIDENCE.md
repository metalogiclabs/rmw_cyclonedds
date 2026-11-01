# Cyclone DDS Jazzy — minimum CDR wire-size preflight

**Evidence date:** 2026-11-02 NZDT. **State:** WARRANTED_BOUNDED for selected C and C++ allocation-before-validation behaviors. General malformed-input memory safety remains UNKNOWN.

## Source lineage

- Upstream Jazzy base: `20b192ae744f2fe56767e68081a46ad0d7f7a0ec`.
- Exact clean candidate: `bbf8c1ad0b2f672f5e95c9ad17ba86cbaee6a2bf`, branch `fix/jazzy-cdr-minimum-wire-preflight-combined`, with only `TypeSupport_impl.hpp` and `serdes.hpp` changed.
- Candidate blobs, pinned in successful research runs:
  - `TypeSupport_impl.hpp`: `86e882abb71f31c08e58dcf7365d3707030f4364`
  - `serdes.hpp`: `8dbd4aafa8e143ad4e02bc3e83f018131822cfb3`
- Preexisting ROS short-header repair: `ros2/rmw_cyclonedds#625`, PR head `73c2fb62b2be3b752b098f44cc6c41b9c4bbe85a`. Both matrix arms apply its *identical source patch* so this is not a duplicate fix.
- All experimental/test-only files are on this research branch, **not** on the clean candidate branch.

## Full source-native regression

- [CI run #41346399171](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41346399171): **SUCCESS**.
- [Evidence artifact #13099187524](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41346399171/artifacts/13099187524), SHA-256 `f4e88daa805e63f173024663fde501d99cb1c56524bc38fce022582cec82808f`.
- Two independently compiled Jazzy RMW libraries; loader path checked through `/proc/self/maps`. 224 process-isolated cases per arm, 448 total (seven ROS message types × sixteen serialized input cases × two RMW implementations × two source arms).
- Cyclone: baseline 7 accepted / 105 defined errors / zero signals / zero timeouts; candidate **identical**. All fourteen valid message controls passed in both arms, and all 28 short-header cases from PR #625 remained defined errors. The candidate was *not* responsible for those existing short-header fixes.
- Bounded C primitive sequence with 1,048,576 claimed `float64` elements and only 1,048,600 bytes of serialized input: baseline error was `unable initialize generic sequence`; candidate error became `invalid data size` prior to C-sequence allocation. Both arms returned `RMWError` and kept valid controls.
- Malformed Fast DDS controls varied in four cases despite no Fast DDS source changes. They are *control variability*, not evidence of Cyclone modification.

## Exact combined source through the public C++ API

- [CI run #41346591201](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41346591201): **SUCCESS**.
- [Artifact #13099436824](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41346591201/artifacts/13099436824), SHA-256 `5cf7a8c9101908eb4208b69c789d4a8ef35e73c0c94b2bd4a473b03c9c05be1c`.
- Genuine `rclcpp::Serialization<test_msgs::msg::UnboundedSequences>`, source-built RMW, valid `uint64` roundtrip, and 8,252-byte malformed input claiming 8,192 `uint64` entries but supplying insufficient payload.
- Largest instrumented allocation request: **65,536 bytes (unmodified) → 151 bytes (exact combined candidate)**, while both reject the malformed input. Explicit loaded-library paths and resource limit in artifact. This is a bounded request measurement, **not** a comprehensive peak-RSS or system-safety guarantee.

## Negative result: nested message sequences

- Independently explored on `research/jazzy-cdr-nested-minwire-20261102`, [run #41346696651](https://github.com/metalogiclabs/rmw_cyclonedds/actions/runs/41346696651) (FAILED expected rejection criterion).
- The code still reaches `resize_field` for a malformed nested `BasicTypes` sequence after the conservative one-byte-per-element check. Under a ~256 MB virtual memory limit, the input (131,136 bytes claiming 131,072 nested elements) returned `RMWError` saying **unable to resize field**, not early **invalid data size**. Three valid nested-message controls passed.
- Hence **NOT WARRANTED:** all nested-message allocations are preflighted, the high-memory fuzz report is resolved, or arbitrary malformed input is safe. An introspection-derived *minimum wire bytes per nested object* is a separate CANDIDATE research direction requiring safe treatment of empty messages.

## Epistemic disposition

- **WARRANTED_BOUNDED:** selected primitive C sequence and typed C++ vector preflights, source-pinned native tests.
- **REJECTED:** interpretation that this combined patch comprehensively solves the independent high-memory fuzz residual.
- **UNKNOWN:** sanitizers on all message families, nested allocation preflight, Jazzy/Humble/Kilted equivalence, full CI on upstream PR, release/backport state.
- **NEXT:** submit a narrowly scoped upstream patch citing the two source-native CI runs, and keep nested minima as separate investigation. Do not duplicate PR #625, do not claim that its short-header fix is ours.
