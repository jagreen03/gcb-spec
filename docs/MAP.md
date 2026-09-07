# Repository file map

Every tracked file in the five repos. **U** = the architecture owner must
understand it. **K** = just know it exists. Generated files and bulk data are
collapsed to one line.

## Owned decision — the fabric IS these files (all **U**)

| file | what |
|---|---|
| `gcb-spec/architecture.md` | this fabric, one page: five repos + data path + doc pointers |
| `gcb-spec/registers.yaml` | MMIO register map — single source of truth; `defects:` + `design_decisions:` (DD-001) blocks |
| `gcb-spec/docs/adr/ADR-001-cascade-adc-reset.md` | reset the analog noise floor at every cascade stage boundary |
| `gcb-spec/docs/adr/ADR-005-Single-Slope-Readout.md` | Single-Slope CIS is the receiver; ΔΣ branch retired |
| `gcb-spec/docs/adr/README.md` | ADR-002/003/004 reserved, unfiled |
| `gcb-spec/carry_save_streaming_contract.md` | Vortex accumulator → optical pilot stream format (M_AXIS_CS, Q17.14, block-float 32→12) |
| `gcb-spec/vortex_integration_notes.md` | compute-side tap into Vortex 3.0 (`result_if`, `tcu_result_t`, `is_tile_final`, `VX_CFG_*`) |
| `gcb-spec/bench_emulation_parameters.md` | physical parameters of the 8-input optical reduction cell (⇄ `mmi_tree_model.py`) |
| `gcb-rtl/rtl/greencoyote_top.sv` | pilot top-level integration |
| `gcb-rtl/rtl/greencoyote_pilot_regs.sv` | MMIO register block (implements `registers.yaml`) |
| `gcb-rtl/rtl/greencoyote_axi_lite_wrapper.sv` | AXI-Lite front end to the register block |
| `gcb-rtl/rtl/greencoyote_photonic_sequencer.sv` | drives the optical cascade / reduction fire sequencing |
| `gcb-rtl/rtl/greencoyote_cs_lane_fifo.sv` | dual-clock carry-save lane FIFO (Vortex clk ↔ pilot clk) |
| `gcb-rtl/rtl/greencoyote_ss_tdc.sv` | shared 6 GHz Gray TDC + 4-phase capture, 64 channels |
| `gcb-rtl/rtl/greencoyote_ss_calib.sv` | fixed-point 3-point calibration back-end |
| `gcb-rtl/rtl/greencoyote_dac_if.sv` / `greencoyote_adc_if.sv` | bench-loopback DAC / SPI-SAR-ADC interfaces |
| `gcb-rtl/integration/VX_tcu_tilefinal_tag.sv` | `is_tile_final` / `fmt_d` wrapper around `VX_tcu_core` (belongs in Vortex tree) |
| `gcb-rtl/integration/VX_tcu_shim_q1714.sv` | PE word → Q17.14 → `M_AXIS_CS` serialiser (belongs in Vortex tree) |
| `gcb-rtl/integration/VX_tcu_q1714_convert_pkg.sv` | bit-exact fp32/int32 → Q17.14 arithmetic, shared by shim + TB |
| `gcb-rtl/integration/VX_tcu_tilefinal_sva{,_bind}.sv` | SVA that the tag wrapper preserves accumulator ordering |
| `gcb-spec/models/readout/ss_readout_mc.py` | charge-domain Monte-Carlo model of the single-slope readout (the number the bench must hit) |
| `gcb-rtl/sim/golden_ss_readout.py` | fixed-point golden model — RTL calib must bit-match this |

## Contract / analysis — evidence behind the decisions

| file | what | |
|---|---|---|
| `gcb-papers/data/readout/spice/SPICE_RESULTS_V3.md` | comparator + gate closure; CONDITIONAL GO, v_comp_noise sweep, g_m–C fallback | U |
| `gcb-papers/data/readout/spice/SPICE_RESULTS_V2.md` | discharge-mode ramp redesign; ramp INL retired as limiter | U |
| `gcb-papers/data/readout/spice/SPICE_RESULTS.md` | V1 ramp NO-GO (superseded, kept for provenance) | K |
| `gcb-papers/data/readout/rtl/RTL_REPORT.md` | RTL verification, 6 GHz timing (carry-select, CML clock), energy 0.55 fJ/MAC | U |
| `gcb-papers/data/readout/ANALYSIS.md` | early single-slope MC sweeps + first CONDITIONAL GO | K |
| `gcb-papers/p1-cascaded-reduction/optical_reduction_paper.md` | paper 1 draft (+ `references.bib`) | U |
| `gcb-papers/p2-rfi-interconnect/rfi_paper2.md` | paper 2 draft | U |
| `gcb-papers/p3-unified-matmul/paper3_optical_multiply_reduce.md` | paper 3 draft | U |
| `gcb-papers/shared/{bib,figures}` | shared bibliography + figures for the drafts | K |
| `gcb-rtl/sim/tb_ss_calib.sv` | Icarus ↔ golden bit-exact, 10 000 conversions | K |
| `gcb-rtl/sim/tb_ss_tdc.sv` | Gray / 4-phase / channel-isolation property checks | K |
| `gcb-rtl/sim/tb_ss_energy.sv` | one-window toggle-count harness for the energy number | K |
| `gcb-rtl/sim/greencoyote_tb.sv` / `tb_cs_fifo_path.sv` | pilot data-plane + M_AXIS_CS FIFO-path TBs | K |
| `gcb-rtl/integration/tb/tb_VX_tcu_*.sv` + `stubs/` | Q17.14 convert + full-shim bit-exact TBs (Verilator/Icarus) | K |
| `gcb-rtl/results/post_route_baseline/*.rpt` | Vivado post-route timing/util/power baseline | K |
| `gcb-papers/data/readout/spice/mc_v2/*.json`, `summary*` | MC sweep outputs (flicker, corner, v_comp_noise, spiceN46/53) | K |
| `gcb-papers/data/readout/ramp_inl/*.csv` + `meta.json` | 9-corner measured ramp-INL curves fed to `ss_readout_mc.py` | K |
| `gcb-papers/data/readout/spice/comparator_noise.json`, `cmp_noise_spectrum_*.txt` | comparator noise roll-up + BSIM4 `.noise` spectra | K |
| `gcb-papers/data/readout/spice/ramp_corners.json`, `ramp_wave_*.txt` | raw V1 ramp-generator SPICE dumps (decimated) | K |

## Toolchain — just know it exists (all **K**)

| file | what |
|---|---|
| `gcb-spec/regen.py` | emits register views into gcb-rtl / gcb-host / gcb-dashboard from `registers.yaml` |
| `gcb-rtl/rtl/generated/greencoyote_regmap_pkg.sv` | generated — SV register constants |
| `gcb-host/include/generated/greencoyote_regmap.hpp`, `proxy/generated/regmap.py` | generated — C++ / Python register views |
| `gcb-dashboard/src/generated/registers.ts` | generated — TS register view |
| `gcb-spec/scripts/setup_spice_env.sh`, `docs/spice_setup.md` | build ngspice + BSIM-CMG(OSDI) + ASAP7, no root |
| `gcb-spec/models/readout/spice/env_setup.sh`, `.../xyce_build_notes.md` | SPICE env bootstrap; Xyce build attempt (blocked) |
| `gcb-spec/models/readout/spice/harness/*.py` | ramp-INL extraction, MC-corner driver, comparator-noise roll-up, summariser |
| `gcb-spec/models/readout/spice/tb/*.cir`, `*.pm` | ASAP7 SPICE decks (ramp, comparator, `.noise`) + OSDI/proxy model cards |
| `gcb-rtl/sim/run_ss_tb.sh`, `run_pilot_tb.sh` | Icarus test runners |
| `gcb-rtl/sim/ss_energy.py` | VCD toggle-count → fJ/MAC |
| `gcb-rtl/sim/mmi_tree_model.py` | optical-cascade precision/noise numerical model (⇄ `bench_emulation_parameters.md`) |
| `gcb-rtl/scripts/build.tcl`, `impl.tcl`, `constraints/*.xdc` | Vivado OOC synth/impl + timing constraints |
| `gcb-rtl/.github/workflows/*.yml`, `integration/tb/*.sh`, `tcu_tfr_config.sh` | CI + Vortex-config sweep scripts |
| `gcb-host/proxy/gcb_proxy.py` | FastAPI MMIO proxy / sovereign safety supervisor |
| `gcb-host/include/greencoyote_pilot.hpp` | C++ pilot driver |
| `gcb-host/tools/hf_manifest_gen.py` | HuggingFace model-manifest generator |
| `gcb-dashboard/src/GreenCoyoteDashboard.jsx` | React dashboard component |
| `gcb-spec/concepts/README.md` | caveat for the AI-generated concept renders (not CAD, not photos) |
| every `README.md`, `.gitignore`, `.gitattributes` | repo-level orientation / VCS config |
