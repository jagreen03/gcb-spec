# GreenCoyote-Bay — Architecture

GCB / ODIN_Bridge is a hybrid photonic–electronic inference fabric: a RISC-V
Vortex 3.0 tensor core streams partial products into a cascaded **optical**
carry-save reduction fabric, the analog optical result is digitised once by a
single-slope CIS readout, and an FPGA pilot exposes the whole thing over MMIO.

## Five repositories

| repo | role | owns |
|---|---|---|
| **gcb-spec** | source of truth | register map (`registers.yaml` + `regen.py`), ADRs, the two integration contracts, the readout behavioural model |
| **gcb-rtl** | pilot RTL + Vortex-side shim | `rtl/*.sv` (synthesised), `integration/*.sv` (belongs in the Vortex tree), testbenches, Vivado scripts |
| **gcb-host** | host software | C++ pilot driver, Python MMIO register simulator (`gcb_proxy.py` — corrected 2026-09-12, `TKT-032`: no FastAPI code, a self-checking simulator against the generated register map, not an HTTP proxy), HF model-manifest tool |
| **gcb-dashboard** | operator UI | React fabric-monitoring dashboard |
| **gcb-papers** | arXiv drafts + evidence | p1 cascaded reduction, p2 RFI interconnect, p3 unified matmul; all readout SPICE/RTL analysis data |

`regen.py` in gcb-spec is the only writer of the generated register views in
gcb-rtl, gcb-host and gcb-dashboard — never hand-edit those.

## Data path

```
Vortex 3.0 TCU  ──►  Q17.14 carry-save stream  ──►  optical cascade  ──►  single-slope readout  ──►  MMIO  ──►  host
 (VX_tcu_core       (M_AXIS_CS AXI4-Stream,        (8-input reduction     (discharge-mode C_int,      (SS_READOUT      (gcb_proxy
  result_if)         one record per tile-final,     cells, block-float      chopped/AZ comparator,      block            safety
                     NUM_LANES beats)               32->12 bit scaling)     6 GHz Gray TDC,             0xB0-0xC0)       supervisor)
                                                                           3-pt calibration)
```

1. **Compute tap.** `integration/VX_tcu_tilefinal_tag.sv` mirrors the core's
   `mdata_queue` ordering to raise `is_tile_final` on the last-K accumulator
   writeback per (m,n) sub-tile — governed by
   `vortex_integration_notes.md` §8.
2. **Carry-save stream.** `integration/VX_tcu_shim_q1714.sv` converts each PE
   word to Q17.14 two's-complement (RNE, saturating) and serialises one
   `M_AXIS_CS` record per tile-final — governed by
   `carry_save_streaming_contract.md` §4–§6.
3. **Optical cascade.** The pilot (`greencoyote_photonic_sequencer.sv`,
   `greencoyote_cs_lane_fifo.sv`) drives the discrete 8-input reduction cells;
   precision/noise are modelled in `gcb-rtl/sim/mmi_tree_model.py`, parameter
   sheet `bench_emulation_parameters.md`. ADR-001: the analog noise floor is
   reset at every stage boundary.
4. **Single-slope readout.** `greencoyote_ss_tdc.sv` (shared 12-bit Gray
   counter at 6 GHz, 4-phase 24 GS/s capture, 64 channels) +
   `greencoyote_ss_calib.sv` (fixed-point 3-point quadratic calibration,
   bit-exact to `gcb-rtl/sim/golden_ss_readout.py`). ADR-005 selects this
   architecture; the Charge-Balancing ΔΣ branch is retired.
5. **MMIO + host.** `greencoyote_pilot_regs.sv` / `greencoyote_axi_lite_wrapper.sv`
   present `registers.yaml`; `gcb-host/proxy/gcb_proxy.py` is the sovereign
   safety supervisor above it; `gcb-dashboard` renders live state.

## Governing documents

| concern | document |
|---|---|
| register map (all consumers) | `registers.yaml` (+ `docs/adr/`, `DD-001` design decision) |
| Vortex compute tap | `vortex_integration_notes.md` |
| accumulator → optical stream (result egress) | `carry_save_streaming_contract.md` |
| memory → optical modulators (operand ingress) | `docs/streaming_dma_architecture.md` |
| optical array geometry + inbound-bandwidth sizing | `docs/optical_geometry_spec.md` (LOCKED: N=64, L=16, T_fire=500 ps) |
| optical-cell physical parameters | `bench_emulation_parameters.md` ⇄ `gcb-rtl/sim/mmi_tree_model.py` |
| readout architecture choice | `docs/adr/ADR-005-Single-Slope-Readout.md` |
| readout evidence (SPICE, RTL, MC) | `gcb-papers/data/readout/spice/SPICE_RESULTS_V3.md`, `.../rtl/RTL_REPORT.md` |
| SPICE toolchain (ASAP7/ngspice) | `docs/spice_setup.md`, `scripts/setup_spice_env.sh` |
| repo-by-repo file index | `docs/MAP.md` |

## Open items

* CONDITIONAL GO on the readout: comparator noise (53 µV, BSIM4 surrogate ±16 %)
  needs a commercial transient-noise histogram to become an unconditional GO.
* ADR-002/003/004 reserved, unfiled.
* Thermal register block (0x40–0x5C) documented but unimplemented (DEFECT-003).
