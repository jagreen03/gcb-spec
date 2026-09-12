# Task 3 — Phase-I Guaranteed Bench (COTS) Physical Bill of Materials

**Closes the citation gap flagged in**
`gcb-wiki/16_hardware_parts_systems_specification.md` (§"Known documentation
gaps", item 1) — `01_streaming_sequence.md` step 8 and
`02_receiver_architecture.md` §"Phase I — Guaranteed Bench" both cite
`gcb-spec/task3_physical_bom.md §3` as the source for the two matched
PD+TIA detection chains; that file did not exist anywhere in the
repository set until this document.

## Epistemic status — read before treating any line item as sourced

**This is a parametric bill of materials, not a procurement record.** No
line item below has been vendor-quoted, purchased, bench-populated, or
measured. Every electrical/optical requirement (full-scale voltage, ENOB
target, wavelength, SPI timing) is taken directly from already-committed,
already-locked repository sources — `greencoyote_adc_if.sv`,
`02_receiver_architecture.md`, `carry_save_streaming_contract.md` — and is
real. The **specific candidate part numbers** named alongside those
requirements are split into two honesty tiers, marked individually:

- **`[CANDIDATE — parametric fit]`**: a real, commercially available part
  from a real manufacturer that this document's author has reasonable
  confidence matches the stated requirement, offered as a concrete starting
  point for a vendor quote. **Not verified against a current distributor
  listing, datasheet revision, or stock status, and not cross-checked
  against `greencoyote_adc_if.sv`'s exact timing by simulation or bench
  test.** Treat as "a good place to start," not "the selected part."
- **`[TBD — vendor survey not performed]`**: the parametric requirement is
  fully specified; no specific candidate part is named because this
  document's author does not have high enough confidence in any single
  specific part number to offer one responsibly (this applies to most of
  §1 and §2 below — specialty telecom/photonics components are far less
  reliably recalled than catalog analog-IC parts, and a wrong specific
  claim here is worse than an honest gap).

Per this program's own standing discipline (`gcb-wiki/14`, `gcb-wiki/16`):
do not assume a part is correct before it is proven. This document is the
**parametric spec and a candidate starting point**; the actual down-select,
quote, and incoming-inspection/datasheet cross-check is a separate,
not-yet-performed procurement step.

---

## 1. Laser Sources & Modulation

**Function:** Phase I's optical stimulus — an O-band continuous-wave source,
isolated from back-reflection, intensity-modulated to the precision the
digital back-end (`greencoyote_dac_if.sv`'s 14-bit parallel DAC bus) can
actually drive.

| Item | Requirement | Candidate | Notes |
|---|---|---|---|
| CW laser source | O-band, **1310 nm** center wavelength (matches `02_receiver_architecture.md`'s O-band invariant and every `gcb-rtl`/`gcb-spec` reference to "O-band sources"); DFB (single-longitudinal-mode, narrow linewidth — needed so modulator-induced chirp and any wavelength-dependent mesh response stay small and repeatable); fiber-pigtailed, singlemode, FC/APC; ≥ a few mW optical output (enough margin for isolator + modulator + splitter + mesh-emulation insertion loss, §2) | `[CANDIDATE — parametric fit]` a 1310 nm DFB laser diode in a fiber-pigtailed benchtop or butterfly-packaged module from a benchtop photonics supplier (e.g., Thorlabs' or a comparable vendor's 1310 nm DFB laser diode source line) | Exact model, output power bin, and whether a benchtop laser-diode controller/driver unit is bundled or separate is a vendor-quote decision, not specified here |
| Optical isolator | 1310 nm band, in-line fiber-pigtailed, singlemode, FC/APC; isolation ≥ 30 dB single-stage (≥ 2 stages if back-reflection from the splitter/mesh-emulation network in §2 proves to destabilize the DFB — not yet characterized) | `[TBD — vendor survey not performed]` | Placed immediately after the laser source, before the modulator, per standard DFB protection practice — not yet confirmed against this specific bench's actual back-reflection budget |
| Optical intensity modulator | O-band (1310 nm) compatible; **linear (not digital on/off) intensity control with effective ≥ 8-bit resolution** over its usable linear range, so the modulator itself does not become the bench's accuracy floor ahead of the ≈10.8-bit ENOB target (§3); driven from `greencoyote_dac_if.sv`'s 14-bit parallel DAC word via the driver stage below; bandwidth only needs to cover the bench's `fire` strobe cadence, not a high-speed telecom line rate | **DECIDED (`TKT-028`, 2026-09-12): linear VOA**, `[TBD — vendor survey not performed]` for the specific part | **Executive decision, not a vendor pick**: VOA over a LiNbO₃ Mach-Zehnder modulator. Rationale — (1) this row's own requirement already states bandwidth only needs to cover the bench's low-rate `fire` cadence, not a telecom line rate, which removes an MZ modulator's one real advantage over a VOA for this application; (2) an MZ modulator's transfer function is fundamentally a cosine-squared interferometric response requiring an active bias-point (quadrature) servo to get ANY usable linear region at all — a whole bias-stabilization subsystem Phase I does not otherwise need, directly against this program's own Phase-I purpose of de-risking the summation/ratiometric physics with the FEWEST new unknowns, not the most; (3) a VOA's attenuation-vs-control-voltage response, while still needing calibration, is commonly a smooth, monotonic function over its usable range with no interferometric lock required — a much more direct path to an 8-bit-linear (or lookup-table-linearizable) target. This reasoning was already flagged as the deciding factor in this row's own prior text ("if bandwidth/linearity needs are modest enough") — by (1) above, they are. The specific VOA part remains `[TBD]`: needs 1310 nm rating, fiber-pigtailed (FC/APC, matching §2), analog-voltage-controlled attenuation, a monotonic response over its usable range, and a control bandwidth far exceeding the bench's own `fire` cadence (trivial for essentially any COTS VOA at this bench's timescales) |

| DAC-to-modulator analog driver stage | Converts `greencoyote_dac_if.sv`'s 14-bit parallel digital word into the VOA's analog control voltage — (a) a parallel-input DAC, (b) a driver/buffer stage scaling the DAC's output onto the VOA's control range | **DAC**: `[CANDIDATE — parametric fit]` Analog Devices AD9767 — a dual 14-bit, parallel-CMOS-input DAC. **Driver**: `[CANDIDATE — parametric fit]` a precision, low-offset CMOS op-amp in the general class Analog Devices markets for DAC-output signal conditioning (e.g., an AD8605-class part), configured as a current-to-voltage converter (AD9767 is current-output) followed by a scaling/level-shift stage | **Why AD9767 specifically**: `greencoyote_dac_if.sv`'s own header comment already anchors its bus timing on "DAC5672/AD9767-class" generic parallel-DAC timing — that reference was an *illustrative analogy*, not a selection, when it was written; this ticket elevates it to an actual candidate because it is a real, well-known 14-bit parallel-input part whose timing the RTL was already modeled on, and it matches the bus width exactly. **Why this driver class, not a telecom modulator-driver IC**: the VOA decision above means the drive target is a low-bandwidth analog control voltage, not a GHz-class RF modulator drive — a high-speed telecom driver IC would be both the wrong voltage range and substantial overkill/added noise risk for this application. **Not yet calculated**: the exact op-amp gain/scaling-resistor values, which depend on the specific VOA's control-voltage range — itself still `[TBD]` above; this is a real, acknowledged blocking dependency, not an oversight. |

---

## 2. Passive Optics & Coupling

**Function:** gets light from the laser/modulator (§1) to the two
detection taps (§3) with a known, stable loss — and, because
`gcb-pic-core` (the real photonic mesh, "Part 8" of `gcb-wiki/16`) **does
not yet exist as a layout, let alone a physical device**, this section is
necessarily a **bench emulation of the mesh's coupling/summation function
using passive COTS fiber optics**, not a literal interface to silicon that
isn't built yet. This is the correct and intended Phase-I posture per
`02_receiver_architecture.md`: Phase I exists specifically to de-risk the
summation/ratiometric-cancellation physics and the detection chain
*independently* of the PIC.

| Item | Requirement | Candidate | Notes |
|---|---|---|---|
| Fiber array connectors | Singlemode, 1310 nm-rated, FC/APC (angle-polished, to control back-reflection into the isolator/laser of §1) at every patch point | `[TBD — vendor survey not performed]` | Standard telecom-grade FC/APC patch cables/connectors; no array-specific (MT-ferrule) connector is required YET because there is no physical multi-channel PIC facet to mate to — if/when `gcb-pic-core` produces a real fiber-array-coupled device, this line item will need to be revisited against that device's actual facet pitch and connector standard |
| PM (polarization-maintaining) splitters | 1310 nm-rated, PM fiber (to keep the modulator's and the eventual mesh's polarization-dependent response well-defined and repeatable across the reference and result paths — PM is the correct choice here specifically *because* non-PM fiber would let the two tap paths' polarization states drift independently and add an uncontrolled, uncalibratable error term); split ratio(s) sufficient to create a reference tap and a result tap from one source leg (a 1×2 or 1×N PM splitter, N chosen once the emulated mesh fan-out below is fixed) | `[TBD — vendor survey not performed]` | |
| 8×8 unitary-mesh **bench coupling emulation** | A passive, fixed (non-reconfigurable) optical network built from COTS PM splitters/combiners that stands in for the eventual integrated 8×8 unitary mesh's summation behavior at the level Phase I actually needs to test: **one reference leg carrying total input power, one result leg carrying a fixed-coefficient carry-save-weighted combination** — not a literal 8×8 unitary transform, since no physical device implementing one exists yet | `[TBD — vendor survey not performed]` | **This is explicitly a bench proxy, not a claim that an 8×8 unitary mesh has been built.** The exact fan-out/weighting topology of this emulation network is an open design task, not specified by this document — it should be derived from `carry_save_streaming_contract.md` §5's reconstruction math applied to whatever fixed coefficient set the Phase-I demonstration chooses, which has not been done yet |

---

## 3. Detection & Readout Chain (Matched Taps)

**Function:** the two matched PD+TIA+ADC chains cited by
`01_streaming_sequence.md` step 8 and `02_receiver_architecture.md`'s Phase
I datapath — **Tap 0 (Reference / total input power)** and **Tap K
(Result / carry-save-weighted sum)**. "Matched" is the load-bearing word:
the ratiometric reconstruction (`ADC_TapK / ADC_Tap0`, `contract §5.3–§5.4`)
cancels global insertion loss **only if both chains have the same
responsivity, the same TIA gain, and run on the same sampling clock** — an
unmatched pair would reintroduce exactly the error term the ratio is
supposed to cancel.

### 3.1 Photodiodes (×2, matched pair)

| Requirement | Candidate | Notes |
|---|---|---|
| InGaAs PIN photodiode, O-band (1310 nm) responsive (InGaAs covers ~900–1700 nm, so 1310 nm is well inside its native response band — the correct material choice, not silicon, which is not usefully responsive at 1310 nm) | `[CANDIDATE — parametric fit]` a fiber-coupled InGaAs photodiode from a benchtop photonics supplier's standard InGaAs PD line (e.g., a small-active-area, fiber-pigtailed InGaAs PIN diode in the general class Thorlabs markets under its "FGA"-prefixed InGaAs photodiode series, or the equivalent from Hamamatsu's InGaAs PIN series) | **Both units of the matched pair must be ordered from the same product line and, ideally, the same date-code/lot** — responsivity matching is a binning/lot property, not guaranteed by part number alone; this is a procurement instruction, not yet executed |
| Low capacitance (small active area) — minimizes the RC time constant feeding the TIA, which otherwise limits how fast the integration/settle timing (`greencoyote_adc_if.sv`'s `SETTLE_CYCLES`) can be without measurement error | Same candidate as above, smallest active-area bin offered | Exact capacitance spec not pinned — depends on the TIA's own input capacitance tolerance (§3.2), not yet co-analyzed |
| Matched responsivity (the two units of the pair, not a spec on one device) | N/A — see procurement note above | |

### 3.2 Transimpedance Amplifiers (×2, matched pair)

| Requirement | Candidate | Notes |
|---|---|---|
| ~1.5 V full-scale analog output (per `02_receiver_architecture.md`: "the TIA output, ~1.5 V full scale" — this is the one analog-voltage node the "no routed analog voltage" invariant in §4 below permits, and only because it never leaves the eval board) | `[CANDIDATE — parametric fit]` a dedicated fiber-optic-receiver transimpedance amplifier IC in the general class of Analog Devices' "AD8015"-type part (a low-cost TIA historically marketed specifically for photodiode-to-voltage conversion in fiber-optic links) | The exact transimpedance gain setting needed to map this bench's actual expected photocurrent range onto 1.5 V full-scale has **not been calculated** — that requires a photocurrent estimate this document does not have (depends on laser power, §1/§2 losses, and photodiode responsivity, §3.1) |
| Matched gain (the pair, not a single-unit spec) | Same IC, same external gain-setting component (resistor) value on both channels | Gain-setting resistor value not specified — depends on the unresolved photocurrent budget above |
| Low noise (the TIA's own input-referred noise must not be the bench's accuracy floor ahead of the ≈10.8-bit ENOB target) | N/A — evaluate against the candidate IC's own datasheet noise spec once the gain setting above is fixed | Not yet evaluated |

### 3.3 Analog-to-Digital Conversion

| Requirement | Candidate | Notes |
|---|---|---|
| 12-bit SPI SAR ADC, **mode 0 (CPOL=0, CPHA=0)**, read-oriented, MSB-first, a 16-bit total frame with the valid result in the low 12 bits (`RESULT_BITS=12` of a `FRAME_BITS=16` frame — **the exact, binding protocol `greencoyote_adc_if.sv` already implements**, confirmed by direct inspection of the RTL this document is written against) | `[CANDIDATE — parametric fit]` a 12-bit, single- or dual-channel SAR ADC with a simple, command-word-free SPI-compatible serial interface — structurally, the simplest match to `greencoyote_adc_if.sv`'s default `CMD_WORD = 16'h0000` (the RTL never actually encodes a command; it just clocks bits) is an ADC family that does not require a configuration-register write to produce a conversion, in the general class Texas Instruments markets under its "ADS786x" 12-bit SAR family | **This is the single highest-value item in this whole BOM to verify before any purchase**: if the eventually-selected ADC *does* require a real command word (many do, including several otherwise-attractive low-power 12-bit SAR parts), `CMD_WORD` must be changed from its current `16'h0000` default and the RTL re-simulated — a required RTL-side check this document flags but does not itself perform |
| Evaluation board form factor (so the ADC is bench-usable without custom PCB spin for Phase I) | Whichever vendor eval/breakout board accompanies the candidate IC above | Not selected |
| Common sampling clock across both tap channels (§3's own "matched" requirement, architectural not just component-level — both ADC instances, or both channels of one dual-channel part, must be driven from `greencoyote_photonic_sequencer.sv`'s single `conversion_start` strobe, exactly as `01_streaming_sequence.md` step 9 specifies: "both taps on a common clock") | N/A — satisfied by driving two instances of `greencoyote_adc_if.sv` (or reusing one dual-channel ADC) from the same sequencer strobe; no additional part needed | Architectural requirement, already satisfied by the existing RTL's own instantiation pattern (one `greencoyote_adc_if` per tap, both fed by the sequencer) |
| Target ≈10.8-bit ENOB on the reconstructed ratio (not a single-ADC spec — this is the whole chain's target, per `02_receiver_architecture.md`: "target ≈ 10.8-bit ENOB (the clean ratiometric model shows ≈10.3-bit RMS; D3 measures the delivered value)") | N/A | **Not yet measured by anything in this repository set** — `02_receiver_architecture.md`'s own text flags "D3 measures the delivered value" as a referenced future measurement, not a completed one; this BOM does not change that status |

---

## 4. Electrical & Interface Invariants

This section exists to make the **"no routed analog voltage"** rule
(`02_receiver_architecture.md`'s architectural invariant) concrete at the
level of physical boards and connectors for Phase I specifically — the
point at which it is easiest to accidentally violate, because the TIA's
1.5 V analog output is a real, physically probeable node.

- **The rule, stated for this bench:** the photodiode (§3.1) and its
  matched TIA (§3.2) are co-located on the same physical receiver eval
  board (or an immediately adjacent, short, shielded point-to-point
  connection between two small boards treated as one logical unit) **for
  each tap**. The TIA's ~1.5 V analog output is consumed **only** by that
  same tap's ADC (§3.3) — which must also be co-located with, or connected
  to its TIA by the shortest practical shielded link on, the same board or
  board stack.
- **What is allowed to cross the interconnect fabric to the Digital Pilot
  FPGA (`greencoyote_top.sv` / `greencoyote_adc_if.sv`):** **only the
  12-bit digital SPI word** (`adc_data[11:0]`, plus the `adc_sclk` /
  `adc_cs_n` / `adc_mosi` / `adc_miso` SPI signal set itself, which are
  digital logic-level signals, not analog voltage nodes) — confirmed
  directly against `greencoyote_adc_if.sv`'s own port list: the module's
  only connection to the photonic sequencer is `adc_data[11:0]` /
  `adc_valid` / `conv_fault`, all digital.
- **What this rule explicitly forbids, for both taps:** routing the TIA's
  analog output pin to any connector, backplane trace, cable, or
  board-to-board link other than the short, local link to its own ADC. No
  analog voltage node from either tap may appear on a shared bus, a
  multi-board backplane, or any cable run back to the FPGA carrier.
- **Matched-pair corollary:** because both taps must be matched (§3), this
  invariant applies **identically and separately to each tap's own
  PD+TIA+ADC sub-assembly** — there are two independent analog-local
  islands, not one shared analog domain feeding two digitizers.
- **Verification status:** this is a design rule for the bench's physical
  layout, not yet a measured or inspected property of any built hardware
  — no Phase-I board has been populated, so this invariant has not yet
  been checked against a physical layout. It should be a explicit
  incoming-inspection/layout-review checklist item once board layout
  begins.

---

## Vendor/SKU down-select status (summary)

| Section | Item | Status |
|---|---|---|
| §1 | CW laser source | CANDIDATE (parametric fit) |
| §1 | Optical isolator | TBD |
| §1 | Intensity modulator | **DECIDED: linear VOA** (`TKT-028`); specific part TBD |
| §1 | DAC-to-modulator DAC | CANDIDATE (parametric fit) — AD9767 (`TKT-028`) |
| §1 | DAC-to-modulator analog driver | CANDIDATE (parametric fit) — precision op-amp I-to-V + scaling stage (`TKT-028`); exact gain blocked on the VOA's own control-voltage range |
| §2 | Fiber array connectors | TBD |
| §2 | PM splitters | TBD |
| §2 | 8×8 mesh bench coupling emulation topology | TBD (design task, not a component) |
| §3.1 | Photodiodes (matched pair) | CANDIDATE (parametric fit); lot-matching procurement step not executed |
| §3.2 | TIAs (matched pair) | CANDIDATE (parametric fit); gain setting not calculated (depends on an unresolved photocurrent budget) |
| §3.3 | SAR ADC + eval board | CANDIDATE (parametric fit); **command-word compatibility with `greencoyote_adc_if.sv`'s `CMD_WORD=16'h0000` default is the one item that MUST be checked against the real datasheet before purchase** |

**Net effect of this document:** the citation gap (a missing file) is
closed, and every electrical/optical requirement the existing,
already-locked repository sources actually specify is captured in one
place. **No part has been purchased, no part has been bench-validated, and
the CANDIDATE entries above are starting points for a vendor quote, not a
completed down-select.** `TKT-028` (2026-09-12) resolved §1's modulator
architecture (VOA, decided) and put first candidates on file for the DAC
(AD9767) and driver stage (precision op-amp I-to-V + scaling) — the exact
driver gain/scaling values remain blocked on the VOA's own control-voltage
range, which is still `[TBD]`. The photocurrent budget (§3.2, `TKT-026`)
and the mesh-emulation topology (§2) remain concrete open engineering
tasks this document surfaces, not resolves.

## Related

- `gcb-wiki/01_streaming_sequence.md` — step 8 (this document's §3) and
  step 9 (`greencoyote_adc_if.sv`).
- `gcb-wiki/02_receiver_architecture.md` — the Phase I / Phase II receiver
  split this document's §3 is the Phase I half of.
- `gcb-wiki/16_hardware_parts_systems_specification.md` — Parts 12/13
  (the RTL-side bench-loopback interfaces this BOM's COTS analog chain
  attaches to) and the documentation-gap entry this file closes.
- `gcb-spec/carry_save_streaming_contract.md` §5 — the ratiometric
  reconstruction math both tap chains feed.
- `gcb-rtl/rtl/greencoyote_adc_if.sv` — the binding SPI protocol §3.3's
  ADC candidate must match.
