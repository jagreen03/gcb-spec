# Task 3 physical bill of materials — discrete 8×8 ratiometric reduction cell

Sourcing breakdown for the Phase I Task 3 bench (Objective O3). Pairs with
[`bench_emulation_parameters.md`](bench_emulation_parameters.md) (component
*specs* → Task 1 model parameters) and
[`carry_save_streaming_contract.md`](carry_save_streaming_contract.md) /
[`vortex_integration_notes.md`](vortex_integration_notes.md) for the ratiometric
readout the bench must physically realize.

**Architecture the BOM builds.** The Analog-ECC pivot replaced the single-output
combiner with a **ratiometric two-tap readout**: every reduction cell drives two
detectors — **Tap 0 (reference)** ∝ total input power, **Tap K (result)** ∝ the
weighted carry-save sum — and the cell output is `ADC(Tap K) / ADC(Tap 0)`.
Global insertion loss and common gain/power drift divide out; per-tap
**Mode-Dependent Loss (MDL)** does not, and nulling it with the pilot's
per-channel trim to ≤ ≈ 0.02 dB is the D3 acceptance criterion. The discrete
bench therefore needs, versus a plain combiner bench: a per-channel **tap
splitter**, a **second combiner tree + detector + ADC channel**, and
**per-channel trim elements in the result arm** (the physical stand-in for the
mesh weights / `CH_GAIN_TRIM`).

**Framing.** Civil test-and-measurement procurement; no defense or military
content.

**Placeholders.** `[VERIFY]` = confirm current part number / availability with
the vendor; `[QUOTE]` = obtain a formal quote before the budget is finalized.
All prices are conservative rough-order-of-magnitude (ROM) USD list estimates,
rounded up, single-unit (no volume discount) — for SBIR Phase I budget-narrative
sizing, not a purchase order.

---

## 0. Configuration tiers

| | **Minimum (4-input, 2 global-trim)** | **Target (8-input, per-channel-trim)** |
|--|--|--|
| Leaf channels `n_inputs` | 4 | 8 |
| Combiner trees | 2 × 4×1 | 2 × 8×1 |
| Result-arm trim | 2 global VOAs (tap balance only) | 8 per-channel VOAs (MDL sweep + calibration) |
| Detectors / ADC ch | 2 / 2 | 2 / 2 |
| Purpose | first light, loss-regime + ratiometric-cancellation check | full MDL sweep, pilot-calibration validation (D3 gate) |

The minimum tier proves the ratio cancels global loss and gets a first MDL
number; only the target tier can exercise the `mdl_db_sigma` 0 → 2 dB sweep and
demonstrate the pilot calibrating per-channel MDL to the ≈ 0.02 dB threshold.
Recommended buy: minimum tier first, upgrade to target after the loss regime is
known (mirrors `bench_emulation_parameters.md` §6).

---

## 1. Lasers & drivers

| Function | Representative COTS part | Vendor | Qty min / target | Unit est. | Ext. (target) | Notes / model tie-in |
|----------|-------------------------|--------|:---:|--:|--:|----|
| O-band leaf source — **target**: fiber-pigtailed DFB butterfly, ~1310 nm, integrated TEC + monitor PD, > 10 mW | `SFL1310` / `L1310P5DFB` class `[VERIFY]` | Thorlabs / II-VI-Coherent / Gooch & Housego `[QUOTE]` | 4 / 8 | $1,600 | $12,800 | `wavelength` O-band; `p_in_max_w` = 0.1 mW at combiner input (source runs well backed-off) |
| O-band leaf source — **minimum**: fiber-pigtailed Fabry-Pérot LD, ~1310 nm, DIP/TO can | `FPL1009S` / `LPS-1310-FC` `[VERIFY]` | Thorlabs | (4) / — | $420 | — | acceptable for intensity-mod bench; broader linewidth, still fine for the model's linear-drive assumption |
| Laser current + TEC driver, board-level, per channel (current + temperature loop, modulation input) | `CTL200` laser controller `[VERIFY]` | Koheron | 4 / 8 | $1,100 | $8,800 | holds case temp to ≤ ±0.1 K (`temperature_k` *held*, not assumed); TEC loop = future `THERMAL_*` domain |
| Butterfly / TO mount + fiber strain relief | `LM14S2` / `LDM56` class `[VERIFY]` | Thorlabs | 4 / 8 | $650 | $5,200 | one per source |
| Modulation drive — dual 14-bit parallel DAC eval board (matches `greencoyote_dac_if.sv`, 14-bit parallel, ≥ tens of MS/s) | `EVAL-AD9767` / `DAC5672 EVM` `[VERIFY]` | Analog Devices / Texas Instruments | 2 / 4 | $280 | $1,120 | 2 ch/board → 4 boards for 8 leaves; `input_levels = 256` uses 8 of 14 bits, headroom for trim |
| Bias-T / RF combiner (DC bias + AC modulation into the LD driver), DC–1 GHz | `ZFBT-6GW+` `[VERIFY]` | Mini-Circuits | 4 / 8 | $110 | $880 | if the chosen LD driver lacks a summing modulation input |
| **Subtotal — lasers & drivers (target 8-input)** | | | | | **≈ $28,800** | + $880 bias-Ts if needed |

*Minimum tier (4× FP + 4× CTL200 + mounts + 2 DAC boards): ≈ **$9,300**.*

---

## 2. The optical mesh / combiner

A reconfigurable integrated 8×8 unitary MZI mesh is **not COTS** — that is the
Phase II fabricated part. The discrete bench realizes the same *ratiometric
function* with fiber components:

```
  leaf k ──►[ 1×2 tap ]──┬── 10% ──────────────────────────►[ 8×1 comb A ]──► Tap 0 (reference)
                         └── 90% ──►[ VOA k  (mesh weight/ ──►[ 8×1 comb B ]──► Tap K (result)
                                      MDL trim, pilot-set) ]
```

| Function | Representative COTS part | Vendor | Qty min / target | Unit est. | Ext. (target) | Notes / model tie-in |
|----------|-------------------------|--------|:---:|--:|--:|----|
| Per-channel tap splitter — 2×2 SM fused coupler, 1310 nm, **90:10**, FC/APC | `TW1300R2A2` `[VERIFY]` | Thorlabs | 4 / 8 | $185 | $1,480 | 10% leg → reference arm, 90% → result arm; ratio insensitive to exact split |
| Result-arm trim / mesh weight — **electronic** fiber VOA, O-band, 0–30 dB, analog control, < 1 ms | MEMS VOA 1310 nm `EV-MVOA` class `[VERIFY]` | Agiltron / DiCon / OZ Optics `[QUOTE]` | 2 / 8 | $650 | $5,200 | the physical `CH_GAIN_TRIM_CHk`; target tier needs 8 (per-channel MDL null + sweep); minimum tier uses 2 global (one per arm) |
| VOA analog driver — multi-channel 0–5 V DAC board from the pilot | `DAC81408 EVM` `[VERIFY]` | Texas Instruments | 1 / 1 | $250 | $250 | 8-ch, slow (VOA control is quasi-static); driven from the pilot |
| Combiner tree A (reference) — SM fused-fiber **8×1** (target) / **4×1** (min), 1310 nm, FC/APC, uniformity spec'd | `FC1310-70-8-APC` / `FOBC-1-13-8` `[VERIFY]` | Thorlabs / OZ Optics `[QUOTE]` | 1 / 1 | $950 | $950 | `stage_il_db` (excess loss) **measured here** — still the first bench number, even though the ratio cancels its common part; residual = tree-A-vs-tree-B imbalance |
| Combiner tree B (result) — identical part, separately characterized | same as above | same | 1 / 1 | $950 | $950 | tree A vs tree B mismatch is a fixed MDL contribution the pilot calibrates |
| Cascade-stage combiner (short 2-stage cascade, §3.5 of bench doc) | 2× 8×1, as above | | 0 / 2 | $950 | $1,900 | optional Phase I; needed for the depth-invariance check |
| Fiber-optic mating sleeves, FC/APC, panel-mount | `ADAFCPMB2` `[VERIFY]` | Thorlabs | 30 / 60 | $12 | $720 | |
| SM patch cords, 1310 nm, FC/APC, assorted lengths | `P5-1310PMP-2` (SM) `[VERIFY]` | Thorlabs | 20 / 40 | $75 | $3,000 | |
| Fiber management tray / breakout enclosure | `[bench-build]` | — | 1 / 1 | $600 | $600 | |
| **Subtotal — optical mesh / combiner (target 8-input)** | | | | | **≈ $17,940** | incl. optional cascade pair |

*Minimum tier (4× tap, 2 global VOA, 2× 4×1 comb, sleeves/cords): ≈ **$6,600**.*

**Combiner characterization gate** (`bench_emulation_parameters.md` §3.1): launch
a known power into each input in turn on **each** tree, record per-input loss,
uniformity, wavelength dependence, and the tree-A-vs-tree-B balance. That balance
is the dominant fixed MDL term; the VOAs null it.

---

## 3. Receivers & ADCs

Two identical detection chains — one per tap. Matching between them is what the
ratio depends on.

| Function | Representative COTS part | Vendor | Qty | Unit est. | Ext. | Notes / model tie-in |
|----------|-------------------------|--------|:---:|--:|--:|----|
| Detection chain — **target**: variable-gain InGaAs receiver module, DC–200 MHz, transimpedance selectable through **2 kΩ**, NEP / NF spec'd | `OE-200-IN1` `[VERIFY]` | FEMTO Messtechnik `[QUOTE]` | 2 | $3,900 | $7,800 | one figure covers `responsivity_a_w ≈ 0.9`, `tia_r_f_ohm = 2.0e3`, `tia_in_noise_a_rthz ≤ 3e-12`, `tia_noise_figure_db ≤ 3`, `bandwidth_hz ≥ 50e6`; holds ~1.5 V swing at ~0.8 mW |
| Detection chain — **minimum**: fixed-gain amplified InGaAs detector, DC–150 MHz, switched gain | `PDA05CF2` / `PD100B3` `[VERIFY]` | Thorlabs / Koheron | (2) | $1,150 | — | gain steps not exactly 2 kΩ — fold the actual value into the Task 1 model (item 1.1) |
| Bare InGaAs PIN (alt. build with discrete TIA) — fiber-coupled, ≥ 50 MHz, 0.9 A/W, dark ≤ 5 nA | `FGA01FC` `[VERIFY]` | Thorlabs | 0 / 2 | $150 | $300 | only if building PD + discrete TIA instead of a module |
| Discrete TIA eval (paired with bare PIN) — decompensated op-amp / dedicated TIA, ~2 kΩ, low input noise | `OPA858EVM` / `ADA4899 eval` `[VERIFY]` | Texas Instruments / Analog Devices | 0 / 2 | $120 | $240 | alt. build only; a proper 2 kΩ, ≥ 50 MHz, ≤ 3 pA/√Hz design is non-trivial — module preferred |
| Dual ADC + DAC FMC/eval board (Tap 0 + Tap K digitized together), ≥ 12-bit, tens of MS/s, ~1.5 V FS | `THDB-ADA` (dual 14-bit ADC 65 MS/s + dual 14-bit DAC 150 MS/s) `[VERIFY]` | Terasic | 1 | $320 | $320 | `adc_bits` 12–14; both taps on one clock removes inter-ADC skew from the ratio |
| Higher-resolution ADC alternative — dual 16-bit, 105–125 MS/s | `EVAL-LTC2185` (`DC1532`) `[VERIFY]` | Analog Devices | 0 / 1 | $520 | $520 | if 14-bit ENOB is marginal after the chain-noise measurement |
| Capture FPGA (if the pilot card has no FMC site) — mid-range dev board with FMC/HSMC + host link | `DE10-Standard` / `DE10-Nano + adapter` `[VERIFY]` | Terasic | 0 / 1 | $500 | $500 | per `bench_emulation_parameters.md` §1, capture is on the pilot FPGA or the ADC board host |
| Low-noise bench supplies for the receiver modules (± 15 V) | `HMP4040` class `[VERIFY]` (or partner-provided) | Rohde & Schwarz | 0 / 1 | $1,400 | $1,400 | often available in the partner lab — see §6 |
| **Subtotal — receivers & ADCs (target 8-input)** | | | | | **≈ $10,340** | FEMTO receivers dominate; module vs. discrete is the main cost lever |

*Minimum tier (2× PDA05CF2 + THDB-ADA): ≈ **$2,620**.*

---

## 4. Fiber, mounts, consumables, bench build

| Function | Representative part | Vendor | Qty | Unit est. | Ext. | Notes |
|----------|--------------------|--------|:---:|--:|--:|----|
| FC/APC bulkhead patch panel + rack strip | `[bench-build]` | Thorlabs | 1 | $400 | $400 | |
| Fiber inspection scope + cleaner (FC/APC) | `FBP-A / FCC-7020` `[VERIFY]` | Thorlabs / Sticklers | 1 | $650 | $650 | end-face cleanliness dominates fused-coupler loss repeatability |
| Index-matching gel, connector caps, spares kit | assorted | Thorlabs | 1 | $200 | $200 | |
| Cabling, BNC/SMA, DC harness for DAC/VOA/receiver control | assorted | Mini-Circuits / Digi-Key | 1 | $500 | $500 | |
| Enclosure / light-tight cover for the assembled cell | `[bench-build]` | — | 1 | $350 | $350 | stray-light and airflow control for the MDL-drift measurement |
| **Subtotal — consumables & build** | | | | | **≈ $2,100** | |

---

## 5. Cost rollup & SBIR Phase I budget narrative

| Group | Minimum (4-input) | Target (8-input ratiometric) |
|-------|--:|--:|
| 1 — Lasers & drivers | $9,300 | $28,800 |
| 2 — Optical mesh / combiner | $6,600 | $17,940 |
| 3 — Receivers & ADCs | $2,620 | $10,340 |
| 4 — Consumables & build | $1,800 | $2,100 |
| **Subtotal** | **$20,320** | **$59,180** |
| Shipping, tax, quote variance (≈ 12 %) | $2,440 | $7,100 |
| **ROM total** | **≈ $22,800** | **≈ $66,300** |

**Budget-narrative guidance (proposal §12.4, "Materials and supplies — Task 3
discrete reduction cell"):**

- The **minimum 4-input tier (≈ $23k)** is the defensible Phase I materials line:
  it delivers first light, the combiner loss-regime measurement, and the
  ratiometric-cancellation check — the results that de-risk the architecture.
- The **target 8-input tier** is dominated by 8× DFB sources + 8× electronic
  VOAs + 2× low-noise receivers. Options to bring it inside a typical Phase I
  materials envelope:
  - FP lasers instead of DFB butterfly (−$9k), accept broader linewidth;
  - 4 per-channel VOAs + 2 global (−$2.6k), sweep MDL on a 4-channel subset;
  - Thorlabs/Koheron amplified detectors instead of FEMTO (−$5.5k), fold the
    non-2 kΩ transimpedance into the Task 1 model;
  - borrow supplies / capture FPGA from the partner lab (§6).
  A trimmed 8-input build lands near **$35–40k**.
- Long-lead items to quote first: DFB butterfly lasers (8–12 wk), electronic
  MEMS VOAs (6–10 wk), custom-uniformity 8×1 fused combiners (4–8 wk).
- Nothing here is single-source-critical: FP-laser, VOA, and combiner vendors
  are all interchangeable (Thorlabs / OZ Optics / AFW / Agiltron / DiCon).

---

## 6. Partner-provided — NOT Phase I-funded

Per proposal §9.3 (Task 3 partner laboratory), assume access to: optical table
with vibration isolation; calibrated optical power meter + InGaAs head
(`PM100D + S154C` class); optical spectrum analyzer; ≥ 1 GHz real-time
oscilloscope; source-measure units and low-noise bench supplies; fiber
cleave / splice / connectorization tooling; laser-safety enclosure and interlocks
(Class 3R at 1310 nm, ~1 mW, but eye-safety procedures still apply). If any is
unavailable, the SMU/supply and power-meter lines move into the BOM (≈ +$4–6k).

---

## 7. Open decisions (feed the final quote)

- **DFB vs FP leaf sources** — DFB narrows linewidth and stabilizes power vs.
  temperature; FP is 4× cheaper and adequate for an intensity-modulation bench.
  Decide after the TEC-hold stability test (`bench_emulation_parameters.md` §3.2).
- **8 per-channel VOAs vs 4 + 2 global** — 8 is required to demonstrate the full
  per-channel MDL calibration the D3 gate specifies; 4 proves the method on a
  subset at −$2.6k.
- **Receiver module (FEMTO) vs amplified detector (Thorlabs/Koheron)** — module
  gives a spec-clean 2 kΩ / NF / NEP that maps 1:1 to the model; the cheaper
  detector needs its actual transimpedance and noise folded into Task 1 (item
  1.1). Largest single cost lever.
- **14-bit vs 16-bit ADC** — start 14-bit (`THDB-ADA`), escalate to
  `LTC2185` only if the measured chain ENOB is within ~1 bit of 12.
- **Capture on the pilot FPGA vs ADC host** — decides how directly the bench
  exercises the pilot calibration registers; prefer pilot-side capture if an FMC
  site is available.
- **Second combiner set for the 2-stage cascade** — buy in Phase I only if the
  loss regime supports a depth-invariance measurement worth doing before
  Phase II.
