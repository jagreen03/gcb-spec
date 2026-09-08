# Optical array geometry & inbound-bandwidth sizing

**Doc version:** 1.0.0 · **Status:** LOCKED (the parameters below are fixed;
changing any of them re-opens the DMA RTL sizing)
**Role:** System Architect (`ai-agents/AGENT_01_SYSTEM_ARCHITECT.md`)
**Consumes:** `docs/streaming_dma_architecture.md` (this doc resolves its §9
"AXI width and port count are provisional" open item)
**Feeds:** AGENT 03 — the RTL Hand-off Block (§5) is the localparam set for the
Streaming Tensor DMA `*.sv`.
**Related:** `registers.yaml` DMA block `0xC4–0xE4` (map_version 0.6.0) ·
`bench_emulation_parameters.md` (Phase-I discrete cell: N = 4→8; this doc sizes
the **Phase-II integrated array**, N = 64) · `carry_save_streaming_contract.md`
(result egress).

**Framing.** Civil compute-integration engineering. No defense or military
content. No silicon exists — every number is a modelled operating point.

---

## 1. Locked geometry (Task 1)

| symbol | meaning | **locked value** | rationale |
|---|---|---|---|
| `N` | parallel optical **output** channels | **64** | 1:1 with the 64 single-slope readout channels (`greencoyote_ss_tdc.sv`); no channel mux, no readout-side rework |
| `L` | contraction lanes per channel **per fire** (modulator pairs summed on one photodetector) | **16** | keeps per-fire modulator fan-in modest and the DAC-load cadence at a realistic 2 GHz; `L · fires_per_window = K_total` (below) |
| `T_fire` | optical beat period (one accumulate step) | **500 ps** → **2.0 GHz** | fast enough that `fires_per_window` is a power of two (512) and `L` stays small; slower `T_fire` trades directly for larger `L` at constant `K_total` |
| `T_obs` | accumulation / integration window | **256 ns** | fixed by the readout (`ss_readout_mc.py` `T_obs`) |
| `fires_per_window` | `T_obs / T_fire` | **512** | 256 ns / 500 ps |
| `K_total` | MAC accumulated per channel per window | **8192** | `L · fires_per_window = 16 · 512`; matches the readout energy accounting (`E/MAC = E/conversion / K_total`) exactly — this is the consistency check that ties the optical array to the readout |
| operand precision | activation and weight code width | **INT8 / FP8 = 8 bit = 1 B** (sizing case) | matches the bench 256-level (8-bit) modulation (`bench_emulation_parameters.md` §2.1); INT4 / FP4 pack 2 operands/byte and halve every bandwidth number below |

**Mapping.** For an output `y = W · x`: optical channel `n` (n = 0..63)
accumulates `y_n`. On each fire the array takes a length-`L` slice of the
contraction dimension: `y_n += Σ_{j=0..15} W[n, k+j] · x[k+j]`, formed by 16
modulator pairs and summed on channel `n`'s photodetector. The `L = 16`
activations `x[k..k+15]` are **broadcast** to all 64 channels that fire; the
`N · L = 1024` weights are per-channel. After 512 fires each photodetector has
integrated `K_total = 8192` products; the single-slope readout digitises it
once (ADR-005). `blk_exp` / offset-binary handling on the result side is
unchanged (`carry_save_streaming_contract.md` §5).

---

## 2. The memory bandwidth wall (Task 2)

### 2.1 Data consumed per optical beat

| per fire (`T_fire` = 500 ps) | operands | bytes @ INT8 | source |
|---|---|---|---|
| activations | `L` = 16 (broadcast to all `N`) | **16 B** | **streamed from memory** |
| weights | `N · L` = 1024 | **1024 B** | **on-die weight-stationary buffer** (not memory, during the window) |
| operand codes driven onto the modulator bus | `L + N·L` = 1040 | 1040 B | modulator DACs (black box past here) |

### 2.2 Sustained memory bandwidth to hold the cascade 100 % saturated

**Activations — the hard floor, independent of batch reuse:**

```
BW_act  =  L · elem_bytes / T_fire
        =  16 B / 500 ps
        =  32.0 GB/s
```

Per-window activation footprint = `16 B/fire · 512 fires` = **8192 B**
(shared across all 64 channels). At 32 GB/s that drains in exactly 256 ns — it
fills the window with no slack, which is the definition of "saturated".

**Weights — amortised over batch/sequence reuse `B`:**

The weight footprint for one window's contraction work, all channels, is

```
WT_tile  =  N · K_total · elem_bytes  =  64 · 8192 · 1 B  =  524 288 B  =  512 KiB
```

reused across `B` windows that hit the same weight matrix (tokens in a layer,
MoE sub-batch, …):

| `B` (reuse) | `BW_wt = 512 KiB / (B · 256 ns)` | note |
|---|---|---|
| 1 (pure GEMV) | **2.05 TB/s** | infeasible — the weight tile MUST persist across the whole layer, i.e. `B` = tokens processed against that matrix |
| 32 | 64.0 GB/s | |
| 64 | 32.0 GB/s | |
| 128 | 16.0 GB/s | |
| 256 | 8.0 GB/s | |

**Aggregate sustained requirement:**

```
BW_total  =  BW_act  +  BW_wt(B)
          =  32.0 GB/s  +  { 64 | 32 | 16 | 8 } GB/s   for B = { 32 | 64 | 128 | 256 }
```

**Design target: 64 GB/s aggregate** — the 32 GB/s activation floor plus
32 GB/s of weight-refill headroom, which covers weight reuse down to `B ≈ 64`
with margin for descriptor fetch and AXI burst turnaround.

### 2.3 Von Neumann bypass, quantified

A digital INT8 MAC array moving both operands from a register-file/L1 boundary
pays `≈ 2 B/MAC`:

```
digital operand traffic  =  2.048 TMAC/s · 2 B  =  4.10 TB/s   (at the RF boundary)
optical operand traffic  ≤  64 GB/s              (from memory, 0 through the CPU)
```

**~64× less operand movement, and none of it crosses the CPU.** That is the
starvation bypass the fabric exists to deliver.

---

## 3. DMA & AXI4 sizing (Task 3)

### 3.1 AXI4 read master

`BW_port = width_bytes · f_axi · η`, with `η = 0.85` sustained (INCR-256, AR
issue + turnaround overhead).

| config | per-port | ports for ~64 GB/s | verdict |
|---|---|---|---|
| 256-bit @ 300 MHz | 8.16 GB/s | 8 | rejected — too many AXI ports / interconnect pressure |
| **512-bit @ 300 MHz** | **16.3 GB/s** | **2 (ACT + WT)** = 32.6 GB/s sustained, 38.4 GB/s peak | **LOCKED** — meets the 32 GB/s activation floor on the ACT port; WT port covers refill for `B ≥ 64` |
| 512-bit @ 300 MHz ×4 | 16.3 GB/s | 4 = 65.3 GB/s sustained | **build option** — low-batch weight refill, `B ∈ [32, 64)` |
| 512-bit @ 500 MHz | 27.2 GB/s | 2 = 54.4 GB/s | rejected — 500 MHz on a 512-bit datapath needs a hardened NoC / deep pipelining, gives no bandwidth win over 2×512@300, and forces a DMA↔sequencer CDC |

**LOCKED: AXI4-Master, 512-bit data, 300 MHz fabric clock (= pilot `user_clk`),
2 read ports (activation + weight).** A 4-port build variant is defined for the
low-batch weight-refill regime. 300 MHz is chosen over 500 MHz specifically so
the DMA, the descriptor walker, and the sequencer hand-off all sit in **one
clock domain** (`user_clk`); the only clock-domain crossing left is
`user_clk → 2 GHz` at each line-buffer **read** port.

AXI4 attributes: `ID` 4-bit, `ADDR` 48-bit, `AxBURST = INCR`, burst ≤ 256
beats, ≥ 8 outstanding `AR` per port, 4 KiB-boundary burst splitting in the
descriptor walker, read-only (`AR`/`R` only). `ARCACHE` / `ARPROT` from
`DMA_CTRL` (`registers.yaml` 0xC4).

### 3.2 Activation ping-pong line buffer

Unit of hand-off = one window's activation footprint = **8192 B**. Bank size
must also cover the worst-case AXI read round-trip (`≈ 300 ns` DDR/HBM → at
32 GB/s = 9.6 KB in flight):

```
bank_bytes  =  8 KiB (footprint)  +  latency cover + alignment slack
            →  16 KiB per bank,  2 banks (ping-pong)
```

| property | value |
|---|---|
| banks | **2** (ping-pong; bank A drains window k while bank B loads window k+1) |
| bytes / bank | **16 KiB** |
| write port (AXI side) | **512-bit** @ 300 MHz → depth **256** words/bank |
| read port (modulator side) | **128-bit** (`L · 8 b` = 16 B) @ **2.0 GHz** (`T_fire` cadence), fanned to all 64 channels |
| CDC | write 300 MHz ↔ read 2 GHz; dual-clock, Gray pointers, `(* ASYNC_REG *)` — same discipline as `greencoyote_cs_lane_fifo.sv` |

### 3.3 Weight-stationary buffer (distributed, not ping-pong)

The `N · L = 1024` weight operands per fire = 2.05 TB/s of **read** bandwidth,
so the weight store is **distributed one bank per optical channel**:

| property | value |
|---|---|
| banks | **64** (one per optical channel `N`) |
| bytes / bank | **8 KiB** = `K_total · 1 B` (that channel's full weight row) |
| total | **512 KiB** |
| read port / bank | **128-bit** (`L · 8 b` = 16 B) @ **2.0 GHz** → 32 GB/s/bank local, 2.05 TB/s aggregate, fully distributed (≈ 1 BRAM/URAM per bank) |
| write port (AXI side) | **512-bit** @ 300 MHz, address-decoded to (bank, offset); full 512 KiB load ≈ 31.4 µs ≈ **123 windows** |
| double-buffer | **off** by default (single 512 KiB). **On** (1 MiB) for zero-stall weight-tile swap at a layer / MoE-expert boundary |

Consequence: a single-buffered weight store is zero-stall for **`B ≥ 128`**
(refill hides behind ~123 windows of compute). For `B ∈ [32, 128)` use the
4-port AXI variant (§3.1) or turn on the double buffer.

---

## 4. Consistency checks

| check | result |
|---|---|
| `L · fires_per_window = K_total` | `16 · 512 = 8192` ✓ |
| `N · K_total / T_obs = MAC rate` | `64 · 8192 / 256 ns = 2.048 TMAC/s` ✓ |
| activation footprint drains in exactly `T_obs` | `8192 B / 32 GB/s = 256 ns` ✓ |
| optical channels = readout channels | `N = 64` ✓ (no channel mux) |
| bench modulation width = sizing precision | 8-bit / INT8 ✓ (`bench_emulation_parameters.md` §2.1) |
| weight full-load time < `B·T_obs` for `B ≥ 128` | `31.4 µs < 128 · 256 ns = 32.8 µs` ✓ |

---

## 5. RTL Hand-off Block — localparams for AGENT 03

> These are **fixed**. AGENT 03 implements the Streaming Tensor DMA `*.sv`
> against exactly this parameter set. Any change here is an architecture
> decision that comes back through AGENT 01 and re-opens this document.

```systemverilog
// =====================================================================
//  GCB Streaming Tensor DMA — geometry & sizing localparams
//  Source of truth: gcb-spec/docs/optical_geometry_spec.md  (v1.0.0, LOCKED)
//  Register block:  gcb-spec/registers.yaml  DMA 0xC4-0xE4  (map_version 0.6.0)
// =====================================================================

// ---- optical array geometry ----
localparam int N_OPT_CH        = 64;    // parallel optical output channels (= readout channels)
localparam int L_CONTRACT      = 16;    // contraction lanes per channel per fire
localparam int T_FIRE_PS       = 500;   // optical beat period  -> 2.0 GHz
localparam int FIRES_PER_WIN   = 512;   // T_OBS_NS*1000 / T_FIRE_PS   (256 ns / 500 ps)
localparam int T_OBS_NS        = 256;   // accumulation window
localparam int K_TOTAL         = 8192;  // MAC / channel / window   (= L_CONTRACT * FIRES_PER_WIN)
localparam int OPERAND_BITS    = 8;     // INT8 / FP8 sizing width; INT4/FP4 pack 2 per byte

// ---- AXI4 read master ----
localparam int AXI_DATA_W      = 512;   // bits
localparam int AXI_ID_W        = 4;
localparam int AXI_ADDR_W      = 48;
localparam int AXI_MAX_BURST   = 256;   // INCR beats
localparam int AXI_OUTSTANDING = 8;     // AR in flight per port
localparam int AXI_N_PORTS     = 2;     // 1 activation + 1 weight  (set 4 for the low-batch-refill build)
localparam int FABRIC_CLK_MHZ  = 300;   // AXI + descriptor walker + sequencer hand-off, all on user_clk

// ---- activation ping-pong line buffer ----
localparam int ACT_BUF_BANKS   = 2;     // ping-pong
localparam int ACT_BUF_BYTES   = 16384; // per bank  (16 KiB)
localparam int ACT_BUF_WR_W    = 512;   // AXI-side write width (bits)
localparam int ACT_BUF_WR_DEPTH= 256;   // 512-bit words per bank  (ACT_BUF_BYTES*8 / ACT_BUF_WR_W)
localparam int ACT_BUF_RD_W    = 128;   // modulator-side read width  (L_CONTRACT * OPERAND_BITS)
localparam int ACT_BUF_RD_CLK_MHZ = 2000; // T_FIRE cadence (2.0 GHz)

// ---- weight-stationary buffer (distributed) ----
localparam int WT_BUF_BANKS    = 64;    // one per optical channel (N_OPT_CH)
localparam int WT_BUF_BYTES    = 8192;  // per bank  (8 KiB = K_TOTAL * OPERAND_BITS/8)
localparam int WT_BUF_TOTAL_KIB= 512;   // WT_BUF_BANKS * WT_BUF_BYTES / 1024
localparam int WT_BUF_WR_W     = 512;   // AXI-side write width (bits)
localparam int WT_BUF_RD_W     = 128;   // per-channel read width  (L_CONTRACT * OPERAND_BITS)
localparam int WT_BUF_RD_CLK_MHZ = 2000;
localparam bit WT_BUF_DOUBLE   = 1'b0;  // 1 = double-buffer (1 MiB) for zero-stall layer/expert swap

// ---- descriptor ring (mirrors registers.yaml 0xC4-0xE4) ----
localparam int DESC_BYTES      = 32;    // one 2D/3D tensor descriptor
localparam int DESC_WORDS      = 8;     // DMA_DESC_WINDOW 32-bit writes per descriptor  (DESC_BYTES/4)
localparam int RING_DEPTH_ONDIE = 32;   // 2 ** DMA_DESC_RING_BASE_HI.RING_SZ_LOG2 (reset value)

// ---- derived / assertion helpers ----
localparam int MAC_PER_WINDOW  = N_OPT_CH * K_TOTAL;              // 524_288
localparam int ACT_FOOTPRINT_B = L_CONTRACT * (OPERAND_BITS/8) * FIRES_PER_WIN; // 8192
localparam int WT_TILE_B       = N_OPT_CH * K_TOTAL * (OPERAND_BITS/8);         // 524_288
// static checks the RTL should `assert` at elaboration:
//   L_CONTRACT * FIRES_PER_WIN            == K_TOTAL
//   ACT_FOOTPRINT_B                       == ACT_BUF_BYTES / 2
//   WT_TILE_B                             == WT_BUF_BANKS * WT_BUF_BYTES
//   T_OBS_NS * 1000 / T_FIRE_PS           == FIRES_PER_WIN
```

**Bandwidth envelope AGENT 03 must sustain:** activation port **32.0 GB/s**
continuous; weight port up to **32.0 GB/s** (B ≥ 64) or **64.0 GB/s** on the
4-port build (B ≥ 32). Line-buffer read ports run at the **2.0 GHz** `T_fire`
cadence; everything upstream is `user_clk` (300 MHz). Underrun at a fire
boundary is fatal — abort the window, set `DMA_STATUS.UNDERRUN`
(`docs/streaming_dma_architecture.md` §4.1).
