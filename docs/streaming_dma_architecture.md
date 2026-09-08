# Streaming Tensor DMA — inbound operand feed to the optical modulators

**Doc version:** 0.1.0 (draft) · **Status:** proposed — architecture only, no RTL
**Role:** System Architect (`ai-agents/AGENT_01_SYSTEM_ARCHITECT.md`)
**Owners:** systems architecture (this doc) · `gcb-rtl` (pilot-side sequencer,
DAC PHY) · `regen.py` / `registers.yaml` (the MMIO block in §6 — proposal only,
landed by AGENT 03)
**Related:**
`carry_save_streaming_contract.md` (the *result egress* path — this doc is the
*operand ingress* path) · `architecture.md` (data path) ·
`vortex_integration_notes.md` (compute-side tap) ·
`gcb-rtl/rtl/greencoyote_photonic_sequencer.sv` (consumer) ·
`gcb-rtl/rtl/greencoyote_dac_if.sv` (modulator/DAC PHY shape) ·
`gcb-rtl/rtl/greencoyote_cs_lane_fifo.sv` (async-FIFO discipline) ·
`registers.yaml` (`PRECISION_MODE`, `REDUCTION_CTRL`, the ISA block 0x60–0x7C) ·
`docs/adr/ADR-001` (stage-boundary reset).

**Framing.** Civil compute-integration engineering. No defense or military
content.

---

## 0. Scope and the black box

This document specifies the **inbound Streaming Tensor DMA**: the engine that
moves activation and weight tensors from system memory / on-die SRAM to the
**modulator interface** that drives the optical multiply array, at the cadence
the optical core needs to stay saturated across an accumulation window.

```
   [ in scope: this document ]                          |   [ black box ]
   system memory / SRAM -> AXI4 -> Tensor DMA -> ping-pong -> modulator IF / DACs -> optical core -> single-slope readout
                                                        |   (fixed execution block -- ADR-005, ADR-001)
```

The **optical multiply/reduce core and the single-slope CIS readout are a fixed
execution block.** This doc does not touch their internals, their precision
(`PRECISION_MODE`), the `V=Q/C` integrator, the comparator, or the 6 GHz TDC.
The boundary is the modulator-drive DAC bus; everything the optical core does
after that byte lands is out of scope.

**It is the complement of `carry_save_streaming_contract.md`:**

| Path | Direction | Carries | Contract |
|---|---|---|---|
| Carry-save streaming | Vortex accumulators → optical **reduction** cells | resolved 32-bit Q17.14 partial sums (one per lane per reduction) | `carry_save_streaming_contract.md` |
| **Streaming Tensor DMA (this doc)** | system memory → optical **multiply** modulators | activation / weight operand tiles (4–8-bit codes) | this doc |

Together they realise the fabric thesis: **activation vectors in, scalar layer
results out — the theoretical minimum data movement for distributed transformer
inference.**

### 0.1 Inherited invariant — do not widen the converter

`carry_save_streaming_contract.md` §2 is load-bearing here too. The modulator
DACs carry **operand codes**, not wide words: INT4 / FP4 / FP8 / BF16 as
selected by `PRECISION_MODE.MODE_SEL` (4–16 bit, physically-resolvable
modulator ENOB ≈ 8–10 bit). The DMA delivers those narrow codes packed and
aligned; it never streams 32-bit accumulator words to the modulator bus, and no
part of this design is an argument to make the modulator path wider. Widening
the operand path buys modulator drive range and settling time and nothing else.

---

## 1. Boundary & requirement definition (Task 1)

### 1.1 Throughput to saturate the optical cascade in one accumulation window

Anchors (modelled operating point, not silicon):

| quantity | value | source |
|---|---|---|
| accumulation / integration window `T_obs` | 256 ns | `ss_readout_mc.py` `T_obs`; `architecture.md` |
| readout channels (conversions per window) | 64 | `greencoyote_ss_tdc.sv`; RTL report |
| MACs represented per conversion `K_total` | 8192 | readout energy accounting (`E/MAC = E/conv / K_total`) |
| pilot fabric clock `user_clk` | 300 MHz | `carry_save_streaming_contract.md` §1 |
| operand precision | INT4 / FP4 / FP8 / BF16 → 0.5–2 B | `PRECISION_MODE.MODE_SEL` |

Per window: `MACs = 64 × 8192 = 524 288`.
Window rate: `1 / 256 ns = 3.906 MHz`.
**Sustained MAC rate `≈ 2.05 × 10¹² MAC/s`** (2.05 TMAC/s) at this operating
point.

Operand bandwidth depends entirely on **reuse**:

- **Activations** are broadcast across the output dimension of the optical
  tile. For an optical dot-product of width `N` outputs, each activation
  element is consumed by `N` weights per fire → activation element rate
  `= MAC_rate / N`.
- **Weights** are, in the natural mapping, **stationary**: a weight tile is
  loaded once and reused across the whole activation stream that hits it
  (the batch / sequence dimension, reuse factor `B`). Weight refill rate
  `= (tile_elements × elem_bytes) / (B × T_fire)`.

| stream | reuse | bandwidth to saturate (INT8, 1 B) | (FP4/INT4, 0.5 B) |
|---|---|---|---|
| activations, `N = 64` output tile | ÷ 64 | `2.05e12 / 64 × 1 B ≈ 32 GB/s` | `≈ 16 GB/s` |
| activations, `N = 128` | ÷ 128 | `≈ 16 GB/s` | `≈ 8 GB/s` |
| weights, **stationary**, `B = 256` reuse | ÷ 256 | `≈ 8 GB/s` amortised | `≈ 4 GB/s` |
| weights, **no reuse** (`B = 1`, streamed live) | ÷ 1 | `≈ 2.0 TB/s` — infeasible | `≈ 1.0 TB/s` |

**Conclusion.** A weight-stationary on-die weight buffer is not an optimisation,
it is the precondition — without it the weight bandwidth alone is three orders
of magnitude over any plausible memory port. With it, the sustained inbound
requirement is **≈ 16–40 GB/s aggregate** (activation stream + amortised weight
refill), precision- and tile-geometry-dependent.

### 1.2 The architectural trade-off

| | **CPU-managed MMIO streaming** | **Descriptor-ring / autonomous 2D tensor DMA** |
|---|---|---|
| Mechanism | CPU executes `sw` to an MMIO data port (or auto-increment window) for every operand word | CPU writes a few descriptors per tile; a hardware sequencer walks them, issues AXI bursts, fills buffers |
| CPU instruction overhead **during the accumulation window** | 1 store / 4 B → **8 Gstore/s needed for 32 GB/s**; a RV64 core at 1–2 GHz issues ≤ 1 store/cycle ⇒ **≤ 8 GB/s ceiling, ~4× short, and 0 % compute headroom** | **zero instructions** during the window — CPU is free to prepare the next tile or do other work |
| Determinism | poor — operand delivery jitters with cache misses, interrupts, scheduler | high — sequencer prefetches on a fixed cadence, decoupled from the CPU |
| Hardware area | minimal (a data port + a pointer) | a descriptor walker, AXI4 read master, ping-pong buffers, credit logic |
| Portability | any host, any ISA, bring-up friendly | needs the DMA block, but still ISA-agnostic (MMIO ring) |
| Von Neumann starvation | **not solved** — the CPU *is* the bottleneck, exactly the failure mode the fabric exists to avoid | **solved** — data movement is offloaded to a dedicated path; the CPU never touches an operand |

**Decision.** The operand feed is a **descriptor-ring, autonomous 2D tensor
DMA**. CPU-managed MMIO streaming is retained only for (a) control, (b) small
weight patches / LoRA deltas (`LORA_TILE_ADDR` domain), and (c) bring-up and
bench correlation. This mirrors `carry_save_streaming_contract.md` §1: *a
logical contract, not a signalling standard — any producer that presents the
stream participates.*

---

## 2. Memory interface

### 2.1 AXI4 read master

- **AXI4 (full), read-only.** `AR` + `R` channels only; no `AW` / `W` / `B`.
  The DMA never writes back — results leave through the readout + MMIO path.
- **Data width 512 bit (64 B/beat).** At 300 MHz that is `19.2 GB/s` per port.
  Provision **two ports**: one activation, one weight (physically may be one
  wide port with two descriptor contexts and QoS arbitration). Aggregate
  `38.4 GB/s` covers §1.1 with margin. A 256-bit fallback (`9.6 GB/s`/port,
  4 ports) is allowed where the interconnect caps beat width.
- **Bursts:** `AxBURST = INCR`, up to the AXI4 limit of **256 beats**. The
  descriptor walker splits every burst at the **4 KB address boundary** (AXI4
  rule) and at the inner-extent boundary of the tensor descriptor.
- **Outstanding:** ≥ 8 `AR` in flight per port (ID-tagged) to cover DRAM/HBM
  round-trip latency; reorder tolerated (buffers are addressed by descriptor
  position, not arrival order).
- **Alignment:** descriptor `base_addr` recommended 64-B aligned. Unaligned
  head/tail is handled by first/last-beat byte-strobe masking in the reader,
  not by forcing software alignment.
- **Coherence:** non-coherent by default (operands are read-only snapshots);
  an `ACACHE`/`ARPROT` field in `DMA_CTRL` selects device vs cacheable
  attributes for platforms that need it.

### 2.2 Tensor addressing — the 2D descriptor

Matrix tiling, im2col halos, causal masks and padded sequence tiles all reduce
to a strided 2D (optionally 3D) walk:

```
descriptor (32 bytes, little-endian):
  [ 47: 0]  base_addr        byte address of element (0,0)
  [ 51:48]  elem_log2_bytes  0=½B(packed nibble) 1=1B 2=2B 4=BF16 pair …
  [ 67:52]  inner_extent     elements per row  (contiguous run before a stride)
  [ 99:68]  inner_stride     byte stride between elements   (1 elem ⇒ packed)
  [115:100] outer_extent     number of rows
  [147:116] outer_stride     byte stride between rows        (row pitch)
  [155:148] pad_before       rows/elements of zero-fill prepended (halo, mask)
  [163:156] pad_after        rows/elements of zero-fill appended
  [175:164] batch_extent     optional 3rd dim (tiles reusing the weight buffer)
  [207:176] batch_stride     byte stride between batch planes
  [223:208] flags            bit0 LAST  bit1 IRQ_ON_DONE  bit2 WEIGHT(1)/ACT(0)
                             bit3 PRELOAD (fill, do not fire)  [7:4] PRECISION
                             (mirrors PRECISION_MODE for cross-check)
  [255:224] reserved / CRC
```

Zero `inner_stride` = broadcast one element across a row (bias / shared scale).
`pad_before` / `pad_after` emit zero operands without a memory read — the
optical core sees a clean tile edge with no software gather.

The **same 32-byte descriptor is the binary contract** whether it arrives via
the MMIO ring (§6.1) or a custom instruction (§6.2). Software is
source-compatible across both.

---

## 3. Buffering strategy — ping-pong line buffers

### 3.1 Activation line buffers (double-buffered)

Two banks per activation stream. While bank **A** drains to the modulator
interface at the deterministic optical cadence, bank **B** fills from AXI
bursts; they swap at the tile-row boundary.

Depth per bank:

```
depth_bytes  ≥  BW_activation  ×  t_axi_rt_max          (cover worst-case read latency)
             +  1 optical-tile-row worth of operands    (the unit of hand-off)
```

With `BW_activation ≈ 32 GB/s` and `t_axi_rt_max ≈ 300 ns` (HBM-class):
`≈ 9.6 KB` latency cover + one row → round to **16 KB per bank, 2 banks =
32 KB per activation stream**. Parameterised; the real number follows the
optical tile width (black box).

### 3.2 Weight-stationary buffer (single, large)

One buffer sized to hold a **full weight tile** (`N × N` operands at the active
precision), loaded once per `DMA_WEIGHT_TILE` program and reused across the
entire activation stream that hits it (`batch_extent`). This is the §1.1
anti-starvation lever made physical. Refilled only on an explicit weight-tile
change (layer / expert / LoRA-merge boundary). Typical size `N = 64–128`,
INT8: `4–16 KB`.

### 3.3 Clock domains

Three cadences meet at the buffers:

| domain | source | rate |
|---|---|---|
| AXI clock | interconnect / memory | 200–300 MHz |
| pilot fabric | `user_clk` | 300 MHz |
| modulator update | optical fire cadence `T_fire` | deterministic, black-box |

The write side of each buffer is the AXI clock; the read side is the modulator
cadence, gated by the pilot sequencer. The crossing uses the **same dual-clock
async-FIFO discipline already in `greencoyote_cs_lane_fifo.sv`**: Gray-coded
pointers, 2-FF synchronisers, `(* ASYNC_REG *)` on the meta stage. No frequency
or phase relationship is assumed between memory and the optical core.

---

## 4. Flow control

### 4.1 Downstream (DMA → photonic sequencer): credit-based

Bare ready/valid is **not** sufficient at this boundary: once the optical core
starts integrating a window, a mid-window operand stall corrupts the analog
accumulation (the same reason the readout power-gate is static, not
signal-timed — `SPICE_RESULTS_V3.md` §5d, out of scope here but the principle
carries). The feed must be **fully armed before a fire, or the window does not
start.**

Protocol:

1. The sequencer advertises a demand: *"I will consume one operand row every
   `T_fire` for the next `W` fires"* (`W` = window depth in rows).
2. The DMA raises **`dma_armed`** only when ≥ `W` rows for that stream are
   resident in the ping-pong buffers **and** the weight buffer holds the tile.
3. The sequencer issues `fire` / `auto_fire`
   (`greencoyote_photonic_sequencer.sv`) **only while `dma_armed` is set**.
4. Each consumed row returns one **credit**; the DMA reader uses credit-return
   rate + a fixed prefetch distance to pace its `AR` issue.
5. **Underrun is fatal, not a stall.** If a buffer would underrun at a fire
   boundary, the sequencer aborts the window and raises a `cal_err`-class fault
   (`DMA_STATUS.UNDERRUN` sticky), exactly as the carry-save contract drops a
   whole reduction on a bad beat (`carry_save_streaming_contract.md` §7). No
   fire ever proceeds on stale operands.

### 4.2 Upstream (AXI → DMA reader): standard ready/valid

`ARVALID`/`ARREADY` and `RVALID`/`RREADY` are stock AXI4. The reader throttles
`AR` issue to `(credits_outstanding + prefetch_distance)` so it never fills a
buffer past the bank it is allowed to touch. Interconnect backpressure is
absorbed here and, if sustained, prevents `dma_armed` from asserting — which
holds the optical core in `IDLE` rather than starving it mid-window.

### 4.3 The rule

> Backpressure is allowed to reach the sequencer (via `dma_armed` low). It is
> **never** allowed to reach the modulator bus. The optical cadence is either
> fully fed or not started.

---

## 5. Dataflow schematic (Task 3)

```
                          descriptor path (control, low bandwidth)
        ┌───────────────────────────────────────────────────────────────────────┐
        │                                                                       │
  ┌─────┴──────┐   MMIO ring doorbell  /  custom-0 push (§6)                     │
  │   RISC-V   │─────────────────────────────────────────────┐                   │
  │   host /   │                                             ▼                   │
  │   Vortex   │                                    ┌──────────────────┐         │
  └─────┬──────┘                                    │  Descriptor      │         │
        │ (zero instr. during the accumulation      │  Walker / FSM    │         │
        │  window — autonomous from here)           │  (2D/3D strides, │         │
        │                                           │   pad, 4 KB split)│        │
        ▼                                           └───────┬──────────┘         │
 ┌───────────────┐      AR / R (read-only)                  │ burst plan         │
 │ System memory │◄─────────────────────────────────┐       ▼                    │
 │  / on-die SRAM│                                  │  ┌──────────────────┐      │
 └───────┬───────┘                                  └──│ AXI4 Read Master │      │
         │  512-bit beats, INCR ≤256, ≥8 outstanding   │  (2 ctx: ACT/WT) │      │
         ▼                                              └───────┬──────────┘     │
 ┌─────────────────────────────┐                                │ 64 B beats     │
 │      AXI4 Interconnect      │────────────────────────────────┘                │
 │  (QoS: WT refill < ACT)     │                                                 │
 └─────────────────────────────┘                                                 │
                                        ┌─────────────── async FIFO (Gray ptrs) ─┼──┐
                                        ▼                                        │  │
                 ┌───────────────────────────────────┐   ┌──────────────────────┐│  │
   activations → │  Ping-Pong Line Buffers  A ⇄ B    │   │  Weight-Stationary   ││  │
                 │  (fill on AXI clk, drain on T_fire)│   │  Buffer (1×, N×N)    ││  │
                 └──────────────────┬────────────────┘   └──────────┬───────────┘│  │
                                    │  operand rows (packed codes)  │            │  │
                                    ▼                               ▼            │  │
                        ┌───────────────────────────────────────────────┐        │  │
                        │   Modulator Interface / operand DACs           │        │  │
                        │   (greencoyote_dac_if.sv shape: parallel bus,  │        │  │
                        │    per-channel select, sync strobe)            │        │  │
                        └───────────────────┬───────────────────────────┘        │  │
                                            │  credit return (1 per consumed row)│  │
                                            └────────────────────────────────────┘  │
                        ╔═══════════════════ BLACK BOX ══════════════════════╗       │
                        ║  optical multiply array → cascade reduction →      ║       │
                        ║  single-slope CIS readout (ADR-005) → MMIO         ║───────┘
                        ╚═══════════════════════════════════════════════════╝   results
                                                                                egress via
                                                                          SS_READOUT + gcb_proxy
```

Legend: `═` black-box boundary · `⇄` bank swap at tile-row boundary · the
`dma_armed` gate (not drawn) sits between the buffers and the sequencer's
`fire` (§4.1).

---

## 6. ISA / software interface

Two invocation models; the descriptor binary format (§2.2) is common to both.

### 6.1 Baseline — MMIO descriptor-ring command queue

A ring of 32-byte descriptors. Two placements, both supported:

- **On-die ring** (small, e.g. 32–64 entries) written through an
  auto-increment MMIO window — the pattern already used by the BRAM program
  store (`BRAM_WR_ADDR` auto-increment, `BRAM_WR_DATA_HI` commits) and by
  `SS_CAL_IDX` / `SS_CAL_DATA`. Lowest latency to first descriptor; bounded
  size.
- **In-memory ring** — `DMA_DESC_RING_BASE` points at a software-managed ring
  in system memory; the AXI read master fetches descriptors itself. Unbounded
  program length; one extra indirection. The `flags.LAST` bit or `HEAD==TAIL`
  terminates.

Software loop: fill N descriptors → one `sw` to `DMA_DESC_TAIL` (the doorbell)
→ `DMA_CTRL.ARM` (w1p) → poll/IRQ on `DMA_STATUS` or `DMA_IRQ`. **Zero stores
per operand**; ~1 doorbell store per tile.

Pros: no ISA change, works with the stock Vortex build and any host (incl. a
PCIe DMA producer, matching the carry-save contract's portability goal).
Cons: a doorbell MMIO round-trip per descriptor batch (tens of ns), ring
bookkeeping in software.

### 6.2 Optional fast-path — custom RISC-V instruction (Phase II)

A decoupled-accelerator (RoCC-style) port on the Vortex core, using a custom
opcode (`custom-0`, `0x0B`):

```
  gcb.dma.desc   rs1, rs2      # rs1:rs2 = 2 GPRs holding the low 16 B of a
                               #   descriptor; a paired 2nd issue carries the
                               #   high 16 B (or rs1 = pointer to a 32 B block)
  gcb.dma.arm    rs1           # rs1 = window depth W; arms the feed
  gcb.dma.wait                 # fence: retire when DMA_STATUS.RUNNING clears
```

Pros: 1-cycle issue, no MMIO round-trip, fuses into the kernel prologue; the
descriptor never leaves the register file.
Cons: needs a Vortex build flag + decoder + toolchain intrinsics; couples the
fabric to one ISA and one core, which is exactly the coupling
`carry_save_streaming_contract.md` §1 avoids. Therefore **optional, behind a
build flag, and it emits the identical §2.2 descriptor** so kernels written for
the MMIO ring recompile unchanged.

### 6.3 Recommendation

Ship **§6.1 (MMIO descriptor ring)** as v1. Define **§6.2** as an optional
Phase II fast-path with a shared descriptor format. Do not block the operand
feed on an ISA extension.

### 6.4 Proposed MMIO block — **proposal only, hand to AGENT 03**

Additive to `registers.yaml`; `map_version 0.5.2 → 0.6.0`;
`address_space.end 0xC0 → 0xE4` (`addr_width` already 8, stride 4 — room to
0xFC). **AGENT 01 does not run `regen.py`.**

```yaml
# ---------------------------------------------------------------------------
# STREAMING TENSOR DMA DOMAIN  0xC4 - 0xE4   (proposal, streaming_dma_architecture.md)
# ---------------------------------------------------------------------------
- name: DMA_CTRL            # 0xC4
  fields:
    - { name: EN,        bits: [0,0],   access: rw }
    - { name: ARM,       bits: [1,1],   access: w1p }   # arm the feed (needs W rows resident)
    - { name: ABORT,     bits: [2,2],   access: w1p }   # drop in-flight window, flush buffers
    - { name: RING_SRC,  bits: [3,3],   access: rw }    # 0 = on-die ring, 1 = in-memory ring
    - { name: ARCACHE,   bits: [7,4],   access: rw }
    - { name: ARPROT,    bits: [10,8],  access: rw }
    - { name: WINDOW_W,  bits: [27,16], access: rw }    # rows per accumulation window
- name: DMA_DESC_RING_BASE_LO # 0xC8   in-memory ring base [31:0]
- name: DMA_DESC_RING_BASE_HI # 0xCC   [47:32] + ring size log2
- name: DMA_DESC_HEAD      # 0xD0   ro  consumer index
- name: DMA_DESC_TAIL      # 0xD4   rw  producer index; a write is the DOORBELL
- name: DMA_DESC_WINDOW    # 0xD8   wo  auto-increment write port for the on-die ring
                           #             (BRAM_WR_DATA_HI-style: 8 writes commit one descriptor)
- name: DMA_WEIGHT_TILE_LO # 0xDC   weight-tile base [31:0]
- name: DMA_WEIGHT_TILE_HI # 0xE0   [47:32] + tile shape sel; a write triggers the stationary load
- name: DMA_STATUS         # 0xE4   ro
  fields:
    - { name: RUNNING,      bits: [0,0] }
    - { name: ARMED,        bits: [1,1] }
    - { name: WT_LOADED,    bits: [2,2] }
    - { name: UNDERRUN,     bits: [3,3] }   # sticky -> cal_err path
    - { name: DESC_ERR,     bits: [4,4] }   # sticky (bad stride / 4 KB / precision mismatch)
    - { name: ROWS_BUFFERED,bits: [19,8] }
    - { name: LAST_DESC_ID, bits: [31,20] }
```

IRQ routing reuses `IRQ_CTRL` (0x14): add `IRQ_DMA_DONE_EN`, `IRQ_DMA_UNDERRUN_EN`.

---

## 7. Determinism & timing budget

- The **optical fire cadence `T_fire` is the master clock.** Everything
  upstream is prefetch and must run ahead of it.
- `dma_armed` must be asserted **before** the sequencer leaves `IDLE`; it must
  stay asserted for the whole `WINDOW_W`-row window. A drop mid-window → abort
  + `UNDERRUN`.
- Prefetch distance (rows the reader stays ahead) `≥ t_axi_rt_max / T_fire`,
  rounded up, plus one bank. This is the sizing input to §3.1.
- Weight-tile load is **off the critical path**: it completes before `ARM` is
  accepted (`DMA_STATUS.WT_LOADED`), and a tile is reused for `batch_extent`
  windows, so its cost amortises to near zero per window (§1.1).

---

## 8. Data-movement accounting (system level)

Per MAC, the inbound path moves:

```
  activation bytes / MAC  =  elem_bytes / N          (N = optical output width)
  weight bytes / MAC      =  elem_bytes / (N × B)     (B = batch reuse of the tile)
```

At `N = 64`, `B = 256`, INT8: `≈ 0.0156 + 0.00006 ≈ 0.016 B/MAC` inbound.
A digital INT8 MAC array moving both operands from an L1/RF hierarchy pays
`≈ 2 B/MAC` at the register-file boundary and far more if it misses to L2/DRAM.
**Two orders of magnitude less operand traffic per MAC**, and none of it
crosses the CPU — which is the definition of not being Von Neumann-starved for
this workload.

The result side is already bounded by `carry_save_streaming_contract.md`
(one 32-bit scalar per lane per reduction) and the readout (one 12-bit-class
conversion per output group). Inbound + outbound together keep the fabric at
*activation vectors in, scalar results out*.

---

## 9. Open questions / follow-on

- **AXI width and port count** are provisional (§2.1) until the optical array
  geometry `N` and `T_fire` are fixed — those live in the black box / the p3
  unified-matmul work. The bandwidth *method* in §1.1 is stable; the number
  moves with `N`.
- **Weight buffer capacity** follows the tile size; §3.2 gives the formula, not
  a final KB.
- **Descriptor ring placement** — on-die vs in-memory (§6.1). In-memory needs
  the AXI master to fetch descriptors (adds an `AR` context); on-die caps
  program length. Default: on-die ring for v1, in-memory behind `RING_SRC`.
- **Reuse of the existing primitive ISA interpreter.** The pilot already has an
  `EXEC_CTRL` + BRAM program store + loop counters (`registers.yaml` 0x60–0x7C).
  Could the tensor DMA be *driven* by that interpreter (a `DMA_DESC` primitive
  op) instead of a separate ring? Would unify sequencing; needs the
  interpreter's opcode space and semantics reviewed. Flag for a follow-on.
- **QoS between activation and weight refill** on a shared interconnect — §2.1
  assumes weight refill is lower priority; confirm against the tile-change
  cadence of the target models (MoE expert switching is the stress case).
- **Descriptor CRC / fault behaviour** — §2.2 reserves bits for it; decide
  whether a bad descriptor aborts the window or is skipped with `DESC_ERR`.

---

## 10. Hand-offs

- **`registers.yaml` / `regen.py`** — the §6.4 block is a *proposal*. AGENT 03
  (RTL Verifier) owns the YAML edit, the `map_version` bump, and the five
  regenerated consumers. **Hand-off: §6.4 is AGENT 03's.**
- **Modulator-DAC electrical behaviour** — settling time, drive range, code
  ENOB, any `V=Q/C` interaction at the modulator — belongs to AGENT 02.
  This doc stops at "a packed operand code lands on the DAC bus."
  **Hand-off: modulator-DAC analog is AGENT 02's.**
- **Optical array geometry** (`N`, `T_fire`, tile shape) — black box, resolved
  in the p3 unified-matmul track. **Hand-off: geometry is out of the pilot
  architect's lane.**
