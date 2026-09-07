# ADR-005: Single-Slope CIS readout for the GCB receiver

## Status

**Accepted** — 2026-09-07. Supersedes the Charge-Balancing ΔΣ readout branch,
which is **retired**.

(All ADRs now live in `gcb-spec/docs/adr/`. ADRs 002–004 are reserved and were
never filed — see `docs/adr/README.md`.)

## Context

The GCB receiver must digitise each optical GEMM-output group to an
output-referred SNDR the transformer tolerates — the `enob_tolerance.py` study
fixed the collapse knee at **8–9 effective bits ≈ 53 dB**, with a comfortable
pass near **56 dB** — while staying under the digital accumulate-add energy
baseline of **0.02 pJ/MAC** (≈ 20 fJ/MAC).

Two receiver architectures were carried:

1. **Charge-Balancing ΔΣ (first-order, charge-domain).** The photocurrent is
   integrated onto a small cap; a 1-bit quantiser and a feedback charge
   reference null the integrator; the digital output is a decimated bit-stream.
   Attraction: noise-shaping trades bandwidth for resolution; "free"
   oversampling from the accumulation beats.

2. **Single-Slope CIS.** Passive integration of the photocurrent onto `C_int`
   over the 256 ns window (discharge-mode: `C_int` pre-charged, PD sinks
   current); one comparison of the held voltage against a shared ramp; a shared
   Gray counter time-stamps the crossing.

### What the evaluation found

The ΔΣ branch did not survive its own numerical audit:

* **No free oversampling.** The accumulation-phase signal fills the full Nyquist
  band (white increments), so OSR = 1 during integration; legitimate
  oversampling exists only in a short post-accumulation hold window, against
  readout-electronic noise — not enough to shape the quantiser to 53 dB.
* **Every ΔΣ sub-block re-introduces the cost the architecture claims to
  avoid** — the 1-bit quantiser is a comparator with the same input-referred
  noise problem, the feedback charge/reference DAC needs matched unit caps and
  settling energy, the loop needs a clocked comparator or amp per channel, and
  decimation needs a per-channel digital filter. Charge-domain ΔΣ, VCO/ICO
  phase-accumulation, and AFE current-gain variants were each audited and
  **FALSIFIED for a robust PVT implementation** (linearity ↔ phase-noise
  operating-point contradiction with no margin; 1/f up-conversion without an
  impractically fast chopper; INL after calibration ~1 %).

Single-Slope, by contrast, accumulated positive evidence at each gate:

| gate | Single-Slope result | source |
|---|---|---|
| passive integration, no per-channel active analog in the accumulate path | `C_int` = 2 pF MOM + reset switch only | `models/readout/ss_readout_mc.py` |
| **one** silicon conversion gate per output (not per 64–256 products) | one comparator decision + one shared-counter latch | ADR context; V2/V3 SPICE |
| ramp linearity | discharge-mode **cascoded** current sink on `C_ramp`, replica-referenced: slope 4.18–4.22 mV/ns across 9 PVT corners (±1.1 %), INL 0.04–0.11 % of FS raw | `SPICE_RESULTS_V2.md` |
| comparator noise (thermal + residual 1/f) | **53 µV** — SPICE `.noise`, BSIM4 gm-matched to ASAP7, γ_eff ≈ 1.4; analytic roll-up 46 µV | `SPICE_RESULTS_V3.md` §7 |
| 3σ V_os | **3.2 mV** (A_VT = 2.0 mV·µm proxy, output-offset-storage auto-zero) | `SPICE_RESULTS_V3.md` §3 |
| energy | comparator **0.51 fJ/MAC** (statically gated 20 ns decision) + digital back-end **0.039 fJ/MAC** (RTL toggle counts × ASAP7 caps) → **≈ 0.55 fJ/MAC total** | `SPICE_RESULTS_V3.md` §3, `rtl/RTL_REPORT.md` §4 |
| readout SNDR at that noise | worst-corner **p05 = 56.7 dB ≥ 56** across 9 ramp-INL corners × 233/300/398 K; p05 does not cross 56 dB until ≈ 72 µV comparator noise | `SPICE_RESULTS_V3.md` §8, §10 |
| digital back-end | **bit-exact**: Icarus Verilog ↔ fixed-point Python golden model, **10 000 / 10 000** conversions | `gcb-rtl/sim/tb_ss_calib.sv`, `RTL_REPORT.md` §1 |

## Decision

**The GCB receiver is a Single-Slope CIS readout:** discharge-mode passive
integration onto `C_int`; a chopped + auto-zeroed 2-stage preamp + StrongARM
comparator, statically power-gated on the calibration-known crossing; a shared
12-bit Gray TDC at 6 GHz with 4-phase (24 GS/s) capture over 64 channels; a
per-channel 3-point (quadratic) calibration back-end.

**The Charge-Balancing ΔΣ branch is retired.** No ΔΣ artifact was ever committed
to `gcb-spec`; the branch existed only as the architectural audit that produced
the falsification above. Nothing is deleted; this ADR is the record that the
branch is closed and must not be re-opened without new physics.

The prior ΔΣ analysis **made this pivot possible** — the "no free oversampling"
and "every sub-block re-introduces the cost" findings are what redirected effort
to the single-conversion-per-output architecture. It is retired on the strength
of that work, not in spite of it.

## Consequences

* **Verdict is CONDITIONAL GO.** The 53 µV comparator-noise number rests on a
  BSIM4 surrogate (±16 %, band 44.5–61.5 µV straddling the 55 µV gate). The one
  standing item is a **transient-noise histogram on a commercial simulator
  (Spectre, native BSIM-CMG)** to close that uncertainty. Even the pessimistic
  band end keeps readout p05 ≥ 56.5 dB, so the risk is bounded.
* **Register map:** the `SS_READOUT` block (0xB0–0xC0) is the receiver's control
  surface — `SS_TDC_CTRL`, `SS_CAL_IDX`/`SS_CAL_DATA` (auto-increment coefficient
  store), `SS_RAMP_TIMING`, `SS_TDC_STATUS`. map_version 0.5.x.
* **Timing:** the shared 6 GHz Gray counter **must** use carry-select /
  carry-lookahead (ripple carry fails SS/125 °C — see DD-001). The 4-phase
  6 GHz clock generation + distribution is a **CML island**; the counter,
  capture and calibration logic stay static CMOS.
* **Fallback on file:** if the commercial transient-noise sim lands above
  55 µV, `SPICE_RESULTS_V3.md` §11 documents a **g_m–C integrating preamp** that
  decouples gain from the 0.8 V load headroom and removes the noise/current
  inversion — no architecture change, only the first-stage load.
* **DEFECT-001–004** in `registers.yaml` are register-map / RTL-hygiene defects
  (address width, `output reg` vs `assign`, THERMAL block stub, read-decoder bit
  totals). They are **not** ΔΣ-branch defects and are unaffected by this
  decision; they remain tracked as-is.

## References

* `gcb-papers/data/readout/spice/SPICE_RESULTS_V{2,3}.md`
* `gcb-papers/data/readout/rtl/RTL_REPORT.md`
* `gcb-spec/models/readout/ss_readout_mc.py`
* `gcb-rtl/rtl/greencoyote_ss_{tdc,calib}.sv`
* `gcb-spec/registers.yaml` (SS_READOUT block, DD-001)
