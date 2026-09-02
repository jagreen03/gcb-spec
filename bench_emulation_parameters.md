# Task 3 bench emulation — physical component parameters

Component breakdown for the discrete-component 8-input optical reduction cell
(Phase I Task 3 / Objective O3). Every spec below is tied to a parameter in the
Task 1 numerical model (`gcb-rtl/sim/mmi_tree_model.py`, `CellParams`); the bench
exists to replace each modelled parameter with a measured one.

**Scope.** This bench establishes single-cell and short-cascade behaviour with
COTS parts on an optical table. It does **not** establish an integrated 64-unit
cell — that is Phase II. Minimum viable configuration is a 4-input (4×1) cell
matching the published Smolanski & Malka combiner; the target is the full
8-input (8×1) cell the architecture uses.

**Framing.** Civil test-and-measurement work; no defense or military content.

---

## 1. Signal path

```
  N digital       per-channel        fused-fiber        O-band PD        commercial
  8-bit values -> laser + intensity -> combiner tree -> + 2 kOhm TIA -> 10-12 bit -> capture
  (leaves)        modulation          (THE PIVOT)       (~1.5 V FS)     ADC @ ~50 MHz   (pilot FPGA
                                                                                        or host)
```

`N` = 4 (minimum) or 8 (target). The pilot FPGA supplies the drive timing and
the per-channel calibration registers (§5); capture may be on the pilot or on
the ADC board's host.

---

## 2. Component breakdown

### 2.1 Laser sources (leaves)

| Item | Spec | Model parameter |
|------|------|-----------------|
| Count | 4 (min) to 8 (target), one per leaf channel | `n_inputs` |
| Type | O-band DFB **or** Fabry–Pérot laser diode, ~1310 nm | `wavelength` (O-band) |
| Per-channel optical power at full digital value | **0.1 mW (100 µW)** at the combiner input, matched across channels | `p_in_max_w = 0.1e-3` |
| Modulation | Intensity modulation linear in the driving digital value, **8-bit (256-level)** resolution | `input_levels = 256`; linear-drive assumption |
| Power matching | Channel-to-channel launched-power spread to be trimmed by the per-channel gain-trim path (§5); target pre-trim spread `[≤ ±5 %]` | inter-channel gain-match (Task 1.2 adds the tolerance sweep) |

**Temperature stabilization.** DFB and FP diodes drift in both wavelength
(~0.1 nm/K for DFB) and output power with junction temperature. Each source
needs a TEC and a temperature controller holding the case to `[±0.1 K]` over a
measurement run; without it, per-channel power drifts faster than the gain-trim
calibration interval and the combiner-loss measurement (§3) is not repeatable.
The model runs at a fixed `temperature_k = 300`; the bench must *hold* that, not
just assume it. (The pilot RTL's `THERMAL_*` register block, currently
`implemented: false`, is the eventual home for closed-loop TEC control.)

### 2.2 Modulation / drive

| Item | Spec | Note |
|------|------|------|
| Drive | One converter (DAC) channel per laser, or a multi-channel DAC board; ≥ 8-bit, update rate ≥ the ADC sample rate | drives the 256-level per-channel value |
| Linearity | Digital value → optical power transfer characterized per channel; residual nonlinearity folded into the Task 1 model (item 1.1) | model currently assumes linear drive |
| Bias | Above threshold, in the linear L–I region; bias point recorded per channel | |

### 2.3 Combiner — THE PIVOT

| Item | Spec | Model parameter |
|------|------|-----------------|
| Type | COTS fused-fiber coupler tree, **8:1** (target) or **4:1** (minimum), single-mode O-band | tree topology (4×1 → 2×1 in the model) |
| Insertion loss (excess) | **To be measured — this is the single most decision-relevant number the bench produces.** | `stage_il_db` |

The Task 1 stress test shows the entire INT8-equivalent precision margin is
governed by this component:

| Combiner regime | Per-stage excess loss | Total 8:1 | K = 4 cascade margin above 8-bit |
|-----------------|-----------------------|-----------|----------------------------------|
| Near-coherent / low-loss (Smolanski & Malka 2025) | ~0.1 dB | ~0.2 dB | ~2.8 bit |
| Fully mutually incoherent | ~4.5 dB | ~9 dB | ~0.8 bit |

**Characterize the combiner first**, before assembling the full cell: launch a
known power into each input in turn, measure the output, and determine whether
the device sits near the 0.2 dB coherent regime or the ~9 dB incoherent penalty
(and where in between). Everything downstream — TIA full-scale, ADC choice,
whether a cascade beyond K = 4 is feasible — depends on this result. A
fused-fiber tree combining mutually incoherent sources is expected to carry a
large fraction of the 9 dB penalty; a fabricated cascaded-MMI die (Phase II
path) is what targets the 0.2 dB figure. The bench must report which regime the
Phase I component actually delivers.

### 2.4 Receiver & TIA

| Item | Spec | Model parameter |
|------|------|-----------------|
| Photodetector | O-band InGaAs PIN, responsivity **~0.9 A/W** at 1310 nm, dark current `[≤ 5 nA]`, bandwidth ≥ 50 MHz | `responsivity_a_w = 0.9`, `dark_current_a = 5e-9` |
| TIA transimpedance gain | **2 kΩ** (`R_f`) | `tia_r_f_ohm = 2.0e3` |
| Output swing | Must hold **~1.5 V** linear swing at **~0.8 mW full-scale detected optical power** (8 × 0.1 mW × combiner transmission → ~0.69 mA → ~1.375 V across 2 kΩ, plus headroom) | `adc_fullscale_headroom` sets V_fs ≈ 1.5 V |
| Input-referred current noise | `[≤ 3 pA/√Hz]` | `tia_in_noise_a_rthz = 3e-12` |
| Noise figure | `[≤ 3 dB]` excess-noise factor over the R_f Johnson-Nyquist floor | `tia_noise_figure_db = 3.0` |
| Bandwidth | ≥ 50 MHz, matched to the ADC noise-equivalent bandwidth | `bandwidth_hz = 50e6` |

Note the design tension the model exposes: `R_f` must be low enough that ~0.7 mA
does not saturate the TIA, and high enough that Johnson-Nyquist current noise
(`4kTB/R_f`) stays well below shot noise. 2 kΩ with ~0.1 mW/channel is the
modelled operating point; if the combiner loss (§2.3) turns out high, the
detected power drops and `R_f` may need to rise (with a matching drop in
bandwidth or per-channel power) to keep the SNR — a bench iteration.

### 2.5 Digitization

| Item | Spec | Model parameter |
|------|------|-----------------|
| ADC | Commercial high-speed **evaluation board**, **10 to 12 effective bits** | `adc_bits` (12 default; 10 is the stress-test case) |
| Sample / noise bandwidth | ~50 MHz noise-equivalent bandwidth; sample rate in the tens of MS/s | `bandwidth_hz = 50e6` |
| Full-scale input | ~1.5 V, matched to the TIA output swing (§2.4) | `adc_vfs` (derived) |
| Per-stage use | One conversion per reduction stage; the stage sum is re-normalized to the ADC full scale each stage | per-stage `StageScale` re-normalization |

The stress test found ADC bit-depth **second order**: dropping 12 → 10 bits
costs ~0.5 bit of cascade resolution. A 10-bit eval board is an acceptable
Phase I starting point; 12-bit removes the ambiguity. Integral / differential
nonlinearity of the specific board is characterized and folded into the Task 1
model (item 1.1).

### 2.6 Bench infrastructure (shared, not Phase-I-funded)

Provided by the Task 3 partner laboratory (see the Phase I proposal §9.3):
optical table with isolation, calibrated optical power meter, optical spectrum
analyzer, high-bandwidth real-time oscilloscope, source-measure units and bench
supplies, fiber-handling / cleaving / connectorization tooling, laser-safety
infrastructure.

---

## 3. Characterization sequence

1. **Combiner alone (§2.3).** Per-input insertion loss, output vs. summed input
   power, wavelength dependence across the source set. Decide the loss regime.
   *Gate: if the excess loss is near 9 dB, re-derive the TIA / ADC operating
   point and the feasible cascade depth before proceeding.*
2. **Single laser + drive (§2.1, §2.2).** L–I curve, digital-value → power
   linearity, power vs. temperature, TEC hold stability over a run.
3. **Receiver chain (§2.4, §2.5).** Responsivity, dark current, TIA gain and
   linearity to 1.5 V, input-referred noise, ADC INL/DNL and ENOB.
4. **Assembled N-input cell.** Summation linearity, dynamic range, effective
   bits vs. the Task 1 model prediction; define and validate the per-channel
   gain-match calibration (§5).
5. **Short cascade (2-stage, N ≤ 64 emulated).** Stage-by-stage error
   accumulation vs. the model's depth-invariance prediction.

---

## 4. Model-parameter ↔ bench-measurement map

| `mmi_tree_model.py` parameter | Fixed by bench step | Currently |
|------------------------------|---------------------|-----------|
| `stage_il_db` | §3.1 combiner characterization | assumed 0.1 dB/stage (optimistic) |
| `p_in_max_w` | §3.2 laser L–I + power meter | assumed 0.1 mW |
| linear-drive assumption | §3.2 digital→power linearity | assumed linear |
| `responsivity_a_w`, `dark_current_a` | §3.3 detector characterization | datasheet nominal |
| `tia_r_f_ohm`, `tia_in_noise_a_rthz`, `tia_noise_figure_db` | §3.3 TIA characterization | datasheet nominal |
| `adc_bits`, ADC INL/DNL | §3.3 ADC board characterization | assumed ideal 12-bit |
| `bandwidth_hz` | §3.3 chain bandwidth | assumed 50 MHz |
| `temperature_k` (held, not assumed) | §3.2 TEC hold test | assumed constant 300 K |
| inter-channel gain-match tolerance | §3.4 calibration validation | not yet swept (Task 1.2) |

---

## 5. Mapping to the pilot RTL calibration path

The bench per-channel calibration uses the registers already in
`greencoyote_pilot_regs` (`registers.yaml`):

| Bench quantity | Register / field |
|----------------|------------------|
| Per-cell dark / offset removal | `GLOBAL_CAL.DARK_OFFSET` |
| Overall scale to the ADC full range | `GLOBAL_CAL.GAIN_TRIM_GLOBAL` |
| Per-channel launched-power / gain trim | `CH_GAIN_TRIM_LO/HI.TRIM_CH0..7` (0xFF = unity) |
| Lock calibration during a measurement run | `GLOBAL_CAL.CAL_LOCK` (atomic unlock-and-update) |
| Calibration-valid / calibration-error flags | `GLOBAL_CAL.CAL_VALID`, `PILOT_STATUS.CAL_ERR` |

D3 delivers the validated calibration procedure driving these registers; D1's
model (Task 1.2) adds the residual-after-calibration term.

---

## 6. Open decisions

- 4:1 (published component, cheaper) vs. 8:1 (architecture cell) for the first
  assembled cell — likely 4:1 first, 8:1 once the loss regime is known.
- Fused-fiber tree vs. a small fabricated MMI die if a shared foundry run is
  available in the Phase I window (unlikely; Phase II otherwise).
- 10-bit vs. 12-bit ADC board — 10-bit acceptable per the stress test; 12-bit
  preferred to remove ambiguity.
- Capture on the pilot FPGA vs. the ADC board host — affects how directly the
  bench exercises the pilot's calibration registers.
