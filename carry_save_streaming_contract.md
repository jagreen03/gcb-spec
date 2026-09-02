# Carry-save streaming contract — Vortex accumulator → optical pilot

**Contract version:** 0.2.0 (draft)
**Status:** proposed. Defines the logical boundary only. The pilot-side register
and RTL changes in §8 are **required follow-on work and are not yet implemented**
— today's `greencoyote_photonic_sequencer.sv` still truncates `buf_data[i][11:0]`
(the §5 stopgap).
**Owners:** systems architecture (this doc) · `gcb-rtl` (pilot side) · Vortex
integration shim (compute side).
**Related:** `registers.yaml` (`PRECISION_MODE`, `GLOBAL_CAL`, `REDUCTION_CTRL`);
`gcb-rtl/rtl/greencoyote_photonic_sequencer.sv`; `decisions/ADR-001`;
`gcb-papers/p1-cascaded-reduction/optical_reduction_paper.md` §3.4, §4.1.

**Framing.** Civil compute-integration engineering; no defense or military
content.

---

## 1. The boundary

```
  Vortex 3.0 compute unit i                         GreenCoyote-Bay pilot (user_clk, 300 MHz)
  ─────────────────────────                         ────────────────────────────────────────
  Ten-Four tensor core                              per-lane async FIFO      photonic sequencer
   fused dot-product  ──► accumulator ──► writeback   ┌────────────┐  buf_data[i][31:0]  ┌──────────┐
   (INT32 / FP32,        register file    shim +      │  wr: core  │ ─────────────────►  │ NORMALIZE│
    microscale exp)      (tile boundary)  AXI-Stream  │  rd: pilot │  buf_full[i]        │  (BFP)   │
                                          master   ──►│  depth ≥ 2 │ ─────────────────►  │  PACK    │
                                          M_AXIS_CS   └────────────┘ ◄───── buf_clear[i] │  FIRE …  │
                                                                                        └──────────┘
```

One AXI4-Stream channel per compute unit (`M_AXIS_CS`), terminating in one
dual-clock FIFO per unit inside the pilot. The FIFO **is** the buffer-halt buffer
of the paper §3.4: it absorbs per-unit completion skew, and the pilot fires the
optical stage only when every required `buf_full` bit is set. No clock
relationship is imposed between a compute unit and the pilot.

The contract is a *logical streaming contract*, not a signalling standard: any
producer that can present the §6 stream (a Vortex unit, a PCIe DMA from a
commercial GPU, an ASIC engine) participates without changing the reduction
stage.

---

## 2. Architectural invariant: the 32-bit → 12-bit compression (do not "fix" this)

> **This is a deliberate, load-bearing design decision — not a limitation to be
> engineered away. Do NOT propose 16-, 24-, or 32-bit DACs or ADCs. Do NOT
> "widen the optical datapath" or "stop throwing away accumulator bits." The
> compression from a 32-bit accumulator word to a 12-bit converter code is the
> contract, and every reviewer who sees `buf_data[31:0]` feeding a 12-bit DAC
> will want to change it. They are wrong. Read this section before touching the
> converter width.**

Three independent reasons make the 32→12 compression correct:

### 2.1 The physics wall — the optical receiver cannot carry 32 bits

The optical reduction cell's usable resolution is fixed by physics: Poisson shot
noise, Johnson–Nyquist thermal noise on the TIA feedback resistor, and the
converter's own quantisation. It is **not** a function of how many bits we choose
to transmit. The Task 1 model (`gcb-rtl/sim/mmi_tree_model.py`) and the D3 bench
plan put the **effective number of bits (ENOB) of the receive path at ≈ 10–10.8
bits RMS** in the clean case, and — by design (ADR-001 resets the analog noise
floor at every stage) — that figure is **flat with cascade depth** and is held at
**INT8-equivalent (≥ 8 effective bits) after tap-balance calibration**. A 12-bit
DAC/ADC pairing already sits ~1–2 bits above the delivered ENOB. That is the
correct amount of headroom.

Feeding a 32-bit word into this receiver does **not** produce a 32-bit result:

- the top ~11 bits land above the noise floor and are recovered;
- **the bottom ~20 bits are delivered straight into thermal and shot noise and
  are physically indistinguishable from it at the photodetector.**

Those 20 bits cost modulator drive range, converter silicon, power, and settling
time, and buy exactly nothing. **A 32-bit optical converter is a 12-bit optical
converter with 20 bits of very expensive random-number generator bolted on.**

### 2.2 The AI-math reality — the accumulator's width is headroom, not payload

Ten-Four accumulates a dot product in INT32 / FP32. That width exists **strictly
to prevent overflow while thousands of products are summed** — so intermediate
partial sums cannot wrap or saturate mid-reduction. It does **not** mean the
final partial result carries 32 bits of *meaningful* information.

Transformer inference is statistically robust: it depends on the **distribution**
of activations and the **relative** magnitudes across a reduction, not on
bit-exact wide integers. INT8 and FP8 inference — the regimes this fabric targets
— already discard far more than 20 low-order bits per operation with no accuracy
loss, because the model was trained to tolerate exactly that. The quantity the
reduction must preserve is "the sum of these eight lanes, to the precision the
next layer can actually use," and that precision is ≈ 8 effective bits
(INT8-equivalent) — comfortably inside the receiver's ~10-bit ENOB.

Spending silicon to move the accumulator's overflow-headroom bits across an
optical link is spending it to transport noise the model would immediately round
away.

### 2.3 The solution — a block-floating-point sliding window

The 32 bits are **rescaled, not blindly truncated.** Per reduction cell, per
fire, the digital tier:

1. finds the block-maximum magnitude across the (up to) eight lanes and derives a
   **shared block exponent** `blk_exp` (§5.1);
2. extracts, from each lane's 32-bit word, the **12 bits that matter for this
   block** — a window positioned just below full-scale, with `SAT_GUARD` bits of
   headroom above and `NOISE_HEADROOM` bits of margin below (both already fields
   in `PRECISION_MODE`);
3. sends those 12 bits to the 12-bit DAC;
4. passes `blk_exp` **digitally, out of band** (latched register — §5.4, §8) so
   the ADC result is scaled back after conversion and the reduction stays
   numerically closed across a cascade.

This is textbook block floating point: one small shared exponent plus narrow
per-lane mantissas. It preserves the full dynamic range of the 32-bit
accumulator **where the model needs it** (the relative magnitudes within a block)
while only ever driving the optics with the ~12 bits they can physically
resolve. The full algorithm, rounding modes, and sign handling are in §5.

---

## 3. What crosses the boundary

**One data element per compute unit per reduction: the unit's resolved,
fixed-point partial-sum scalar for one reduction lane, as a 32-bit word.**

### 3.1 "Carry-save" is resolved at the fabric, not at the unit

Paper §4.1 speaks of streaming an unresolved `(S, C)` bit-vector pair. The
implemented architecture supersedes that: **the cross-unit carry-save adder is
the optical tree itself.** Each unit emits *one already-resolved* non-negative
integer; the photodetector + ADC perform the deferred carry resolution across the
eight lanes of a cell (ADR-001 resets the analog noise floor at every stage
boundary, so each stage's sum is re-resolved cleanly). Streaming redundant `S`
and `C` from each unit would double the modulator count for no precision gain
under a power-summing combiner and is explicitly **out of contract**.

The tap point on the Vortex side is therefore the **accumulator writeback at the
compute-tile boundary** — a register-file value, already resolved — never the
intra-MAC 3:2-compressor state.

### 3.2 Why the port is 32-bit when the DAC window is 12-bit

`buf_data[i]` is 32-bit because the unit hands the pilot the **full accumulator
word**; the reduction-scale decision (which 12 bits drive the DAC) belongs to the
pilot, which is the only agent with visibility of all eight lanes of a cell at
once (§2.3). The current `[11:0]` truncation in RTL is a stopgap from before this
contract existed and is replaced by the block-floating-point NORMALIZE stage in
§5.

---

## 4. Numeric format

### 4.1 On the wire (Vortex → FIFO)

| Field | Width | Meaning |
|-------|-------|---------|
| `acc_word` | 32 | Two's-complement fixed-point partial sum, format **Q17.14** (17 integer bits incl. sign, 14 fraction). See §4.2 for the FP32 case. |
| carried in `tuser` | 6 | `{nan_inf, clamp_src, cell_lane[3:0]}` — see §6.3 |

`acc_word` is signed. Transformer partial sums are signed; the optical path is
unipolar (intensity ≥ 0). The sign is carried across the DAC boundary by
**offset-binary encoding applied by the pilot** (§5.3), not by the compute unit.

### 4.2 INT32 vs. FP32 accumulator

- **INT32 accumulate (INT8/INT4 inference):** the Ten-Four accumulator is already
  an integer. The shim sign-extends / saturates it into Q17.14 by placing the
  integer at the binary point (`acc_word = sat32(acc_int <<< 14 >>> shift_hint)`),
  where `shift_hint` is the per-tensor microscale left over from INT8 requant.
  No rounding here — the value is exact.
- **FP32 accumulate (FP8/BF16 inference, training-adjacent):** the shim converts
  `float32 → Q17.14` using the Ten-Four **microscale block exponent** as the
  reference scale: `acc_word = rne( acc_f32 * 2^(14 − blk_exp_tf) )`, saturating
  to ±(2^17−2^−14). `blk_exp_tf` is Ten-Four's own per-block scaling exponent,
  emitted alongside the tile; this makes the fixed-point mantissa occupy the top
  of the 32-bit word for the block's dynamic range. `rne` = round-nearest-even.
  NaN/Inf → saturate to full-scale **and** set `tuser.nan_inf` (§7).

The shim is a small, purely combinational-plus-one-register block on the Vortex
core clock. It does **not** talk to other units.

### 4.3 Precision modes

`PRECISION_MODE.MODE_SEL` (`INT4 / FP4 / FP8 / BF16`) continues to select the DAC
packing window **after** the §5 block scaling, exactly as
`greencoyote_photonic_sequencer.sv` does today (`dac_packed` case on `mode_sel`).
The contract adds nothing to `MODE_SEL`; it defines how the 32-bit word upstream
of that packing is produced and scaled.

---

## 5. Resolving 32 → 12: pilot-side block floating point

This is the mechanism behind the §2.3 invariant. The pilot's `NORMALIZE` state
gains a **per-reduction block-floating-point pass**. Block floating point is the
baseline; the rounding step inside it is selectable (truncate, round-nearest-even,
or stochastic). Static truncation alone is rejected — the accumulator's dynamic
range moves per layer and a fixed shift clips or underflows.

### 5.1 Algorithm (per reduction cell, per fire)

Given the 8 lane words `acc_word[0..7]` (absent lanes = exact 0) and the active
lane count `n = queue_depth`:

```
1. mag_max   = max(|acc_word[k]|) over active lanes k
2. blk_exp   = clamp( msb_index(mag_max) - (11 - SAT_GUARD - NOISE_HEADROOM), 0, 31 )
                 # shift so the largest lane lands just below the DAC full-scale
                 # window, leaving SAT_GUARD headroom on top and NOISE_HEADROOM
                 # at the bottom — the fields already in PRECISION_MODE.
3. for each active lane k:
     shifted  = acc_word[k]  >>> blk_exp                  # arithmetic
     rounded  = ROUND(shifted, acc_word[k], blk_exp)      # §5.2
     biased   = rounded + 12'sd2048                       # offset-binary, §5.3
     mant[k]  = clamp(biased, 0, 4095)                    # 12-bit unsigned DAC code
     if (biased != mant[k]) sticky CLAMP  -> cal_err path
   inactive lanes: mant[k] = 0                            # NOT biased (§5.3)
4. drive DAC with mant[0..7]; latch blk_exp and n for the post-ADC step (§5.4)
```

`msb_index` is a priority encoder on a 32-bit magnitude — one level of logic,
off the DSP critical path that owns the current WNS.

### 5.2 Rounding modes

New field (see §8): `REDUCTION_CTRL.ROUND_MODE[1:0]`.

| Code | Mode | Use |
|------|------|-----|
| `00` | Truncate | lowest cost; residual DC bias tolerable for short cascades |
| `01` | Round-nearest-even | default for inference |
| `10` | Stochastic | default for training-adjacent / deep cascades — removes the reduction's accumulated rounding bias across many tiles; dither from a per-lane LFSR (reuse the `greencoyote_dac_if.sv` LFSR pattern, distinct seed per lane) |
| `11` | reserved | — |

Stochastic rounding: `rounded = shifted + (lfsr_frac >= discarded_frac ? 0 : 1)`,
i.e. round up with probability equal to the discarded fractional part.

### 5.3 Sign — offset-binary with post-ADC de-bias

Each **active** lane adds a constant `+2048` before clamping, so every DAC code is
in `[0, 4095]` and the existing unipolar datapath
(`normalized[i] = ... : 12'h000`) is unchanged. The optical sum the ADC returns
is then:

```
adc_sum ≈ Σ_active (true_shifted_k + 2048)  =  (Σ true_shifted_k) + n·2048
```

The pilot subtracts `n·2048` (n = `queue_depth`, **not** 8 — absent lanes were
not biased) after conversion. This costs one bit of signed mantissa range
(≈ ±11-bit effective) and keeps a single unipolar optical pass.

*Phase II option (not in this contract):* full-range bipolar reduction by
splitting positive and negative lanes across the two passes the sequencer already
supports (`PASS_INDEX`), recombined digitally. Deferred — offset-binary is the
baseline.

### 5.4 Post-ADC reconstruction

```
stage_result = ( adc_result_debiased ) <<< blk_exp      # back to Q17.14 scale
```

forwarded to the next cascade stage (or the fabric output) in the same 32-bit
Q17.14 format, so a cascade stage consumes exactly what a compute unit produces —
the contract is closed under cascading, and `blk_exp` never has to cross the
optical link (§2.3 step 4).

---

## 6. AXI4-Stream transport

### 6.1 Channel

`M_AXIS_CS` — one master per compute unit, AXI4-Stream, `ACLK` = Vortex core
clock, `ARESETn` = core reset.

| Signal | Width | Notes |
|--------|-------|-------|
| `TVALID` / `TREADY` | 1 / 1 | standard handshake; `TREADY` from the pilot FIFO write side |
| `TDATA` | 32 | `acc_word`, Q17.14 (§4) |
| `TLAST` | 1 | end of a lane's contribution to one reduction. Baseline: 1 beat per reduction, `TLAST` always 1. Reserved > 1 beat for a future wide-vector lane. |
| `TID` | `$clog2(N)` | source compute-unit id; maps to the existing `ACTIVE_TID` / crossbar routing domain in `registers.yaml` |
| `TUSER` | 6 | `[5] nan_inf`, `[4] clamp_src` (shim already saturated), `[3:0] cell_lane` — which lane of which 8-input cell this beat targets |
| `TKEEP` | 4 | all ones (full word); present for IP-packager compliance only |

`TDEST` is not used at this boundary — one physical stream per unit already
selects the destination FIFO. A shared-stream variant (PCIe DMA producers) uses
`TDEST` = FIFO index and is allowed but not the Vortex path.

### 6.2 Framing and the `buf_full` / `buf_clear` semantics

- **One beat = one lane's partial sum for one reduction.** A reduction *record*
  for an 8-input cell is 8 beats, one into each of 8 lane FIFOs.
- `buf_full[i]` (to the sequencer) = **lane FIFO `i` holds ≥ 1 complete record**
  (writer increments a record counter on each `TLAST` beat; `buf_full[i]` =
  `record_count[i] != 0`). This preserves every existing bit-pattern test in
  `greencoyote_photonic_sequencer.sv` (`queue_full = &buf_full`,
  `is_14gpu_mode`, `queue_depth = Σ buf_full`).
- `buf_clear[i]` (from the sequencer, one cycle, in `DONE` / after capture) =
  **pop one record** from lane FIFO `i` (`record_count[i]--`, advance read
  pointer past that record's beats).
- `buf_data[i]` presented to the sequencer = the head record's single beat
  (`TDATA`). When a wide-vector lane is introduced later, `buf_data[i]` is the
  first beat and the sequencer gains a beat index; baseline needs neither.

### 6.3 Clock domain crossing

The per-lane FIFO is a standard dual-clock (asynchronous) FIFO: Gray-coded
pointers, 2-FF pointer synchronisers, `(* ASYNC_REG *)` on the meta stage — same
discipline as the ADC path already in the sequencer. Write side = Vortex
`core_clk`; read side = `user_clk`. **Minimum depth 2 records** (double buffer:
the unit may begin writing tile *k+1* while the pilot reduces tile *k*);
recommended 4. No `user_clk` ↔ `core_clk` frequency or phase relationship is
required or assumed.

### 6.4 Backpressure

`M_AXIS_CS.TREADY` deasserts when the lane FIFO is full (pilot has not consumed
the previous record — e.g. a stalled reduction, or a slow peer lane holding the
halt gate). The compute unit blocks on the stream write, which is the intended
buffer-halt behaviour: no data is dropped, and the buffer-halt latency bound
(paper §3.4) still holds because it is set by the *slowest producer*, not by the
FIFO.

---

## 7. Error and edge cases

| Case | Contract behaviour |
|------|--------------------|
| FP32 accumulator is NaN/Inf | shim saturates `acc_word` to ±full-scale and sets `TUSER.nan_inf`. Pilot: drop the whole reduction, raise `cal_err`, do **not** fire. |
| Shim saturated a finite value | `TUSER.clamp_src = 1`; pilot proceeds but sets the sticky `CLAMP` status. |
| Block-scale clamp in §5.1 step 3 | sticky `CLAMP` status → `cal_err` path; reduction still fires (clamped lane is a known over-range, not a fault). |
| Fewer than 8 active lanes (14-GPU pass, partial tile) | absent lanes contribute **exact 0**, are **not** offset-biased; de-bias uses `n = queue_depth`. Already consistent with `!buf_full[i] → dac_packed = 0`. |
| Lane FIFO underrun on `buf_clear` | must not happen — `buf_clear[i]` is only asserted by the sequencer after `buf_full[i]` was observed. Writer treats an underrun as a fault (raises a stream error, out of band). |
| Beat ordering | FIFO order within a lane = reduction order. No cross-lane ordering constraint: the pilot fires only when all required `buf_full` bits are set. |
| `blk_exp` disagreement across a cascade | there is none — `blk_exp` is recomputed per stage from that stage's inputs (§5.1); it is carried only far enough to do the §5.4 post-ADC shift. |

---

## 8. Required follow-on (NOT in this change)

This document is the contract. Landing it implies the following, tracked
separately:

1. **`registers.yaml`:**
   - `REDUCTION_CTRL`: add `ROUND_MODE[1:0]` (§5.2). Bump `map_version`.
   - New `BLK_SCALE_STATUS` (RO): `BLK_EXP[4:0]` last used, `CLAMP` sticky,
     `LANE_BIAS_N[3:0]` (= `queue_depth` latched at fire) for host-side
     reconstruction / debug.
   - Consider moving `n·2048` de-bias enable behind a `LANE_BIAS_EN` bit for
     bring-up (bias off = raw unipolar codes for bench correlation).
2. **`greencoyote_photonic_sequencer.sv`:** replace the `buf_data[i][11:0]`
   truncation with the §5.1 BFP `NORMALIZE` pass; add the priority encoder,
   the per-lane stochastic-rounding LFSRs, the offset-binary add, and the
   post-ADC `n·2048` subtract + `<<< blk_exp` in `CAPTURE` / `CAPTURE2`.
   Re-run the 18-assertion TB and the OOC timing check (guard the current WNS).
3. **`greencoyote_top.sv`:** instantiate the per-lane dual-clock FIFOs and the
   `M_AXIS_CS` slave ports; expose `core_clk` as a second clock input.
4. **Vortex integration shim** (in the Vortex tree, not `gcb-rtl`): accumulator
   writeback tap → Q17.14 conversion (§4.2) → `M_AXIS_CS` master.
5. **`mmi_tree_model.py`:** add the offset-binary `+n·2048` term and the BFP
   `blk_exp` quantisation to `simulate_cell` so the model matches the datapath
   the bench will measure.

---

## 9. Open questions

- **Q17.14 range.** 17 integer bits (incl. sign) covers a per-unit partial sum up
  to ±65 535 at unit scale. Confirm against the largest transformer layer /
  batch tile Vortex 3.0 will actually accumulate before a reduction; widen the
  integer part (Q19.12?) if a real workload exceeds it.
- **Wide-vector lanes.** Is one scalar per unit per reduction always sufficient,
  or will a unit ever contribute a short vector (e.g. grouped heads) in one
  record? Baseline says scalar; §6.1 `TLAST` and §6.2 leave room.
- **Shared vs. per-unit stream for the Vortex path.** Per-unit is specified here.
  Revisit if the Vortex 3.0 cluster exposes a single wide AXI-Stream egress
  rather than one per unit.
- **Stochastic-rounding entropy.** Per-lane LFSR is cheap but correlated across
  reductions at the LFSR period. Adequate? Or reseed per tile from a pilot
  counter.
