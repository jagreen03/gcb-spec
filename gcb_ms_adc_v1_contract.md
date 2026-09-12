# Silicon Contract — GCB-MS-ADC-V1

**Treat custom mixed-signal silicon like a REST API contract: a stable,
versioned digital interface + timing spec that digital RTL and physical
(analog/silicon) development build against independently, in parallel,
without either side blocking on the other.** This document is the contract.
`sim/mocks/gcb_ms_adc_mock.sv` (`gcb-rtl`) is the reference implementation
of it — digital consumers build and verify against the mock today; whoever
owns the physical part builds against this same document, independently,
and the mock is retired (or kept as a golden behavioral reference) once
real silicon timing exists.

## Epistemic status

**PRELIMINARY SPECIFICATION — no silicon exists.** This is a digital
interface + timing contract only: a pinout and a cycle-accurate latency
rule, chosen to be implementable and to unblock RTL work, **not** derived
from any measured or SPICE-characterized physical design. Every numeric
value below is an `ESTIMATE/ASSUMPTION` placeholder (same label this
program uses for `gcb-wdm-transceiver`'s own bring-up parameters, e.g.
`MAX_SKEW_CYCLES`) until a real physical implementation either confirms it
or forces a revision — and this document, being the contract, is what gets
revised; the digital side that built against it gets a mechanical
parameter/timing update, not a rearchitecture, which is the entire point of
having the contract in the first place.

**Relationship to existing work — read before assuming this replaces
anything:** this program already has a materially more developed Phase-II
digitization design — the 64-channel, single-slope CIS readout
(`gcb-spec/docs/adr/ADR-005-Single-Slope-Readout.md`, **CONDITIONAL GO**,
SPICE-characterized on ASAP7) with its own digital back-end,
`gcb-rtl/rtl/greencoyote_ss_tdc.sv` + `greencoyote_ss_calib.sv`. **GCB-MS-ADC-V1
is not that part, does not supersede it, and makes no claim of consistency
with it.** It is a deliberately simpler, single-channel, generic contract —
useful specifically because it is simple enough to mock and build against
*today*, for any digital consumer that needs "a 12-bit conversion result N
cycles after a start pulse" without yet committing to the single-slope
architecture's own channel count, Gray-TDC clocking, or calibration
back-end. Reconciling the two — or deciding GCB-MS-ADC-V1 is superseded by
the single-slope design before any silicon is ever built for either — is an
open architecture decision this document does not make.

## 1. Part identity

| Field | Value |
|---|---|
| Part number | `GCB-MS-ADC-V1` |
| Class | Custom mixed-signal IC (or IP block destined for one) — analog-to-digital conversion, single channel |
| Contract version | v1 (this document) |
| Status | Preliminary specification; no RTL-internal, SPICE, or layout work has been done against this specific contract |

## 2. Digital pinout

| Signal | Width | Direction | Description |
|---|---|---|---|
| `sys_clk` | 1 | in | The part's single digital clock domain. **This contract defines exactly one clock domain** — it says nothing about the clock(s) the actual analog core may need internally; any CDC between an internal analog-timing clock and `sys_clk` is the physical implementation's own problem, not exposed here. |
| `rst_n` | 1 | in | Asynchronous, active-low reset. While asserted: `data_out` is driven to `12'h000`, `data_valid` and `conv_fault` are held low, and any in-flight conversion is abandoned (not completed, not reported). |
| `conv_start` | 1 | in | One-cycle strobe. Rising-edge-sampled on `sys_clk`. Begins one conversion. |
| `data_out` | 12 | out | The conversion result. **Valid only in the same cycle `data_valid` is asserted** — not registered/held afterward; a consumer that needs the value later must capture it itself on the `data_valid` cycle. |
| `data_valid` | 1 | out | One-cycle strobe marking `data_out` valid. |
| `conv_fault` | 1 | out | One-cycle strobe, **always coincident with `data_valid`** (never asserted on its own cycle) — this mirrors the existing, already-proven convention in `gcb-rtl/rtl/greencoyote_adc_if.sv` ("a watchdog raises `conv_fault` with a coincident `adc_valid`, data = 0 on fault"), chosen deliberately for consistency rather than inventing a different fault-signaling shape for this new part. When `conv_fault` is asserted on a `data_valid` cycle, `data_out` **must** read `12'h000` that same cycle — a faulted conversion never carries a meaningful result alongside the fault flag. |

No other pins are defined by this contract. In particular: **no SPI bus, no
analog pins, no busy/ready output.** The absence of a busy output is a
deliberate contract choice (§3's rule below covers the same ground a busy
flag would) — a future contract revision may add one if a real
implementation needs to expose it, but v1 does not.

## 3. Timing contract (strict, cycle-accurate)

```
sys_clk      __|‾|__|‾|__|‾|__|‾|__ ... __|‾|__|‾|__|‾|__
conv_start   ____|‾|________________ ... ________________
                 ^ sampled high here (cycle 0)
data_valid   ________________________ ... ______|‾|______
data_out     ----------------------- ... ------<RESULT>---
                                               ^ cycle CONV_LATENCY_CYCLES
conv_fault   ________________________ ... ______?________   (0 on success, 1 on fault — coincident with data_valid either way)
```

1. **Latency is fixed, not a range.** Exactly `CONV_LATENCY_CYCLES` rising
   edges of `sys_clk` after the edge that samples `conv_start` high,
   `data_valid` asserts for exactly one cycle, with `data_out` (and
   `conv_fault`) valid on that same cycle. "Strict" means this count does
   not vary cycle-to-cycle, run-to-run, or with the conversion's own
   result value — a physical implementation with data-dependent or
   PVT-dependent latency does not meet this contract as written; that
   would require a contract revision (e.g. adding a `busy` output so a
   consumer can poll instead of assuming a fixed count), not a silent
   violation.
2. **`CONV_LATENCY_CYCLES` value:** **16**, `ESTIMATE/ASSUMPTION` — a round
   placeholder chosen for this preliminary contract, not derived from any
   measured or simulated physical timing. A real implementation will very
   likely need a different number; when it does, this document's own
   value is what gets revised, and `sim/mocks/gcb_ms_adc_mock.sv`'s
   `CONV_LATENCY_CYCLES` parameter is updated to match — the digital
   consumer RTL built against the mock should need no change beyond
   re-running its own testbench against the new parameter value.
3. **Re-trigger behavior while busy.** If `conv_start` is asserted while a
   conversion is already in flight (i.e., at any point between the
   sampled `conv_start` edge and the resulting `data_valid` edge,
   exclusive of the `data_valid` cycle itself), **that assertion is
   ignored** — no second conversion is queued, no fault is raised, and
   the in-flight conversion's own latency count is unaffected. A
   `conv_start` asserted on or after the `data_valid` cycle begins a new
   conversion normally.
4. **Reset behavior.** `rst_n` low at any point abandons any in-flight
   conversion immediately (no completion, no `data_valid`, no
   `conv_fault` for the abandoned attempt) and returns the part to its
   idle state; the first `conv_start` after `rst_n` deasserts behaves as
   case 1 above, from that point.
5. **Back-to-back conversions.** A `conv_start` asserted on the exact
   cycle `data_valid` is high for the previous conversion is legal and
   begins a new, independent `CONV_LATENCY_CYCLES`-cycle count — there is
   no mandatory idle/settle gap between conversions in this contract (a
   real implementation that needs one must say so in a contract revision,
   not assume a consumer will insert one).

## 4. What this contract deliberately does not specify

- Any analog-side behavior (input range, reference voltage, noise,
  linearity, sampling aperture) — this is a **digital interface contract
  only**. The physical implementation's own analog specification is a
  separate document this one does not attempt to be.
- Power, area, or process node.
- What `data_out`'s 12 bits actually represent physically (this contract
  fixes the digital *shape* of the result, not its calibration,
  linearity, or unit) — consistent with `greencoyote_ss_calib.sv`'s own
  separation of raw-code capture from calibrated interpretation elsewhere
  in this program, should a future revision of this part need one.
- Multi-channel operation. This is a single-instance, single-channel
  contract; a system needing N channels instantiates N copies (or a
  future contract revision defines a multi-channel variant) — it is not
  assumed here.

## 5. Conformance

A digital RTL consumer built against `sim/mocks/gcb_ms_adc_mock.sv` (§2/§3
implemented exactly) is, by construction, built against this contract. A
physical implementation "conforms to GCB-MS-ADC-V1" if and only if it
presents exactly the pinout in §2 and satisfies every numbered rule in §3
with its own real `CONV_LATENCY_CYCLES` value substituted for the
placeholder in rule 2 — at which point this document's own placeholder
value is updated to match, not left stale.

## Related

- `gcb-rtl/sim/mocks/gcb_ms_adc_mock.sv` — the reference behavioral mock.
- `gcb-rtl/rtl/greencoyote_adc_if.sv` — the existing Phase-I COTS SPI SAR
  ADC bench interface (a different, SPI-based contract; `conv_fault`'s
  "coincident with valid, data=0" convention is deliberately shared with
  this document).
- `gcb-spec/docs/adr/ADR-005-Single-Slope-Readout.md`,
  `gcb-rtl/rtl/greencoyote_ss_tdc.sv`, `greencoyote_ss_calib.sv` — the
  existing, more mature, 64-channel Phase-II digitization design this
  contract explicitly does not replace or claim consistency with (see
  "Relationship to existing work" above).
- `gcb-spec/task3_physical_bom.md` — the Phase-I physical BOM this
  contract has no dependency on (GCB-MS-ADC-V1 is a Phase-II-class
  on-die-silicon concept; Phase I stays COTS per that document).
