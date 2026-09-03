# Vortex 3.0 / Ten-Four integration notes — accumulator writeback tap

**Status:** working notes. Source-of-truth for the compute-side half of
`carry_save_streaming_contract.md` (v0.3.0+). Everything here is read off the
cloned upstream tree, not inferred.

**Source mapped:** `vortexgpgpu/vortex`, `VERSION` → `VORTEX_VERSION=3.0`
(`TOOLCHAIN_REV=v3.0.1`), HEAD `9e3a58241` ("docs: drop reports/ and document the
tinygpu synthesis config"). Tensor unit type `VX_CFG_TCU_TYPE = "TFR"` (Ten-Four
Reduction). Paths below are relative to the Vortex repo root.

**Framing.** Civil compute-integration engineering; no defense or military
content.

**Where the clone lives.** `D:\R\S\H\vortex\` — a sibling of the `gcb-*` repos,
**not** a submodule of any of them, and not committed into `gcb-spec`. Apache-2.0
upstream; keeping it external preserves the licensing / academic-publishing
posture the papers rely on.

---

## 1. Tensor-unit module hierarchy

```
VX_execute.sv:126           VX_tcu_unit               (one per core, gated by VX_CFG_EXT_TCU_ENABLE)
  VX_tcu_unit.sv:229          └─ VX_tcu_core   ×BLOCK_SIZE   (BLOCK_SIZE = VX_CFG_ISSUE_WIDTH)
    VX_tcu_core.sv:~600           └─ VX_tcu_fedp_tfr   ×(TCU_TC_M·TCU_TC_N)   one FEDP per output PE
      tfr/VX_tcu_fedp_tfr.sv          ├─ tfr/VX_tcu_tfr_shared_mul / mul_f16 / mul_f8 / mul_f4 / mul_i8 / mul_i4
                                     ├─ tfr/VX_tcu_tfr_align      (shift partials to a common exponent)
                                     ├─ tfr/VX_tcu_tfr_acc        (CSA tree → sign-magnitude significand)
                                     └─ tfr/VX_tcu_tfr_norm_round (LZC + normalize + round → 32-bit word)
    VX_tcu_core.sv:711-746       └─ result landing queue (LUTRAM FIFO, decouples FEDP grid from a stalled consumer)
  VX_tcu_unit.sv:256            └─ VX_lane_gather      (per-block result_if → commit_if[ISSUE_WIDTH])
VX_execute.sv:141            commit_if[EX_TCU·ISSUE_WIDTH +: ISSUE_WIDTH]  →  core commit / scoreboard / RF
```

The FEDP array **free-runs** — no per-register enable. Admission
(`execute_if.ready`, `VX_tcu_core.sv:252`) reserves a landing-queue slot, so a
completed result always has somewhere to land. `FEDP_LATENCY` = 4 (sim) / 5
(Vivado/Quartus) for TFR (`VX_config.toml:273`, `tcu_latency_tfr`).

---

## 2. The accumulator is register-file resident

Ten-Four has **no dedicated accumulator bank**. The MMA C/D tile lives in the
warp GPR/vector file:

- `VX_tcu_pkg.sv:165` — `localparam TCU_RC = 0;` (C/D base register index)
- `VX_tcu_uops.sv:333` — `wire [4:0] rs3 = TCU_RC + 5'(rs3_offset);`
- `VX_tcu_core.sv:502` —
  ```systemverilog
  wire [31:0] c_val = 32'(execute_if.data.rs3_data[i * TCU_TC_N + j]);   // C[i][j] in
  ```
  and the FEDP drives `d_val[i][j]` = `dot(a_row_i, b_col_j) + c_val`
  (`VX_tcu_core.sv:~672`).

Accumulation across the K dimension is the core (or, when
`VX_CFG_TCU_WGMMA_ENABLE`, the `VX_tcu_wgmma` sequencer) **issuing repeated MMA
uops** that read C from `rs3` and write D to `rd` over the same architectural
registers.

**Consequence for the tap:** there is no "final accumulator latch" to hook.
*Every* MMA uop's writeback is an accumulator writeback; the **tile-final** value
is the writeback of the last K-step uop for that output tile. The stream either
(a) carries every MMA writeback and the pilot consumes only tile-final records
(simplest — needs a "last-K" marker from the shim), or (b) the shim filters to
tile-final using `header.eop` / the WGMMA `is_last_uop` flag. Decide in §8.

---

## 3. The tap point

**`VX_tcu_core.result_if`** — `VX_tcu_core.sv:42`, `VX_result_if.master`,
`data_t = tcu_result_t`. One instance **per TCU block** (`BLOCK_SIZE =
VX_CFG_ISSUE_WIDTH`). Driven at `VX_tcu_core.sv:748-761`:

```systemverilog
assign result_if.valid       = setup_valid_r || fedp_done || ~landq_empty;   // :748
wire [RESULT_DATAW-1:0] result_data = landq_empty ? RESULT_DATAW'(d_val) : landq_data;  // :750
for (genvar e = 0; e < TCU_TC_M * TCU_TC_N; ++e) begin : g_result           // :755
  if (`VX_CFG_XLEN > 32)
    assign result_if.data.data[e] = {32'hffffffff, result_data[e*32 +: 32]}; // NaN-box  :757
  else
    assign result_if.data.data[e] = result_data[e*32 +: 32];                 // :759
end
assign result_if.data.header = setup_valid_r ? setup_header_r : mdata_queue_out; // :277
```

This is the clean tile-result boundary: post-normalize, resolved, one 32-bit word
per lane, full header, with `valid` / `ready` backpressure that the pilot FIFO
write side maps onto directly (`result_if.ready` ← FIFO `!full`).

**Alternative tap — `VX_tcu_unit.commit_if`** (post-`VX_lane_gather`,
`commit_t`, `VX_tcu_unit.sv:264`): lane-gathered to full warp width, carries
`rd` / `wr_xregs`, closer to "what the RF sees", but the TCU-internal identity
(block index, PE `e`) is gone. Use only if the shim must sit outside `VX_tcu_unit`.

**Do NOT tap `tfr/VX_tcu_tfr_acc.sv`** `sum_vec` / `carry_vec`
(`VX_tcu_tfr_acc.sv:53-54`): that is the intra-dot-product 3:2 CSA state. It is
resolved to sign-magnitude in the same module (`:66-95`) and normalised to a
32-bit float/int two stages later. Streaming it out is explicitly out of contract
(`carry_save_streaming_contract.md` §3.1).

---

## 4. Data at the tap

`tcu_result_t` — generated by `` `DECL_EXECUTE_T(tcu, `VX_CFG_NUM_TCU_LANES) ``
(`VX_tcu_pkg.sv:416`; macro at `VX_define.vh:573-599`):

```systemverilog
typedef struct packed {
    tcu_header_t                              header;
    logic [NUM_TCU_LANES-1:0][`VX_CFG_XLEN-1:0] data;   // one word per lane
} tcu_result_t;

typedef struct packed {                       // tcu_header_t
    logic [UUID_WIDTH-1:0]   uuid;
    logic [NW_WIDTH-1:0]     wid;
    logic [NCTA_WIDTH-1:0]   cta_id;
    logic [NUM_TCU_LANES-1:0] tmask;
    logic [...]              pid;
    logic                   sop, eop;         // start/end-of-packet — use eop for tile-final
    logic [PC_BITS-1:0]     PC;
    logic                   wb;
    logic [NUM_XREGS-1:0]   wr_xregs;
    logic [NUM_REGS_BITS-1:0] rd;             // destination reg (C/D tile base + offset)
    logic [BYTESEL_BITS-1:0] bytesel;
} tcu_header_t;
```

- **Payload word** (`data[e]`, `e = i*TCU_TC_N + j`, `e ∈ 0..TCU_TC_M·TCU_TC_N-1`):
  - **float modes** (FP16 / BF16 / FP8 / TF32 output): IEEE-754 **binary32**.
    NaN-boxed — bits `[63:32] = 32'hFFFFFFFF` — when `VX_CFG_XLEN = 64`.
  - **integer modes** (INT8 / INT4): **int32**, `int_result = {int_hi, acc_tc[24:0]}`
    (`tfr/VX_tcu_tfr_norm_round.sv:163`).
  - selected by `fmt_d` — `tfr/VX_tcu_tfr_norm_round.sv:165`:
    `assign result = is_int ? int_result : fp_result;`
- The word is a **resolved scalar** — carry-save is already collapsed (§3).

---

## 5. The fp32/int32 → Q17.14 shim

Placement: a small block **on the Vortex core clock**, downstream of
`VX_tcu_tilefinal_tag` (which supplies `is_tile_final` and `fmt_d` aligned to
`result_if.valid`), feeding the `M_AXIS_CS` master. It does not talk to other
units or other lanes.

Draft reference implementation: **`gcb-rtl/integration/VX_tcu_shim_q1714.sv`**.
For each tile-final result beat it latches the `NUM_LANES` PE words, converts
each (one time-shared combinational converter), and serialises them as
`NUM_LANES` AXI4-Stream beats on one `M_AXIS_CS` master —
`TUSER = {nan_inf, clamp, cell_lane[3:0]}`, `TLAST` on the last lane, `TID =
cfg_tid`. Non-tile-final beats are accepted and dropped. A `2·NUM_LANES`-deep
egress FIFO decouples the serialiser from `M_AXIS_CS.TREADY`.

The conversion arithmetic is factored into the dependency-free package
`VX_tcu_q1714_convert_pkg` and verified bit-exact against an independent
real/longint reference by `gcb-rtl/integration/tb/tb_VX_tcu_q1714_convert.sv`
(~1.8M vectors, RNE + TRUNC, `errors=0`). That test caught one real bug: on the
sign-magnitude fp path, `TRUNC` truncated the *magnitude* (toward zero) instead
of flooring toward −∞ — now consistent with the int path (`>>>`) and the pilot's
`ROUND_MODE=00`.

### 5.1 Integer modes (INT8 / INT4 inference)
`data[e]` is already an integer (`fmt_d[4] == 1`). `acc_word =
sat32( rne( $signed(int32) <<< (14 − int_prescale) ) )`, where `int_prescale` is
the per-tensor requant right-shift — drive it from a CSR so a large
K-accumulated INT8 sum lands inside Q17.14 (a plain `<<< 14` overflows for K
beyond a few dozen; see §9 "Q17.14 range"). Exact when `int_prescale ≤ 14`.

### 5.2 Float modes (FP8 / BF16 inference, training-adjacent)
`acc_word = rne( f32_to_fixed(data[e], 2^(14 − blk_exp)) )`, saturating to
±(2^17 − 2^−14). `blk_exp` reference scale:

| Build | Source of `blk_exp` |
|-------|---------------------|
| `VX_CFG_TCU_MX_ENABLE = true` | `VX_tcu_mx_scale.sv` emits per-row / per-col 8-bit scale factors `sf_a[TCU_TC_M][…]`, `sf_b[TCU_TC_N][…]`; combine the row/col pair for PE `e` into the block exponent. This is the "microscale exponent" the contract's §4.2 refers to. |
| MX disabled (**shipped default**) | No hardware microscale. The shim derives its own block exponent from the fp32 result magnitudes of the lanes in the record (a max-exponent reduction — the same operation the pilot does in `carry_save_streaming_contract.md` §5.1, just earlier). The Vortex-side exponent hint then becomes optional; the pilot's BFP pass is authoritative. |

NaN / Inf on `data[e]` → saturate `acc_word` to ±full-scale **and** set
`TUSER.nan_inf` (contract §7).

### 5.3 What crosses to the pilot
The FIFO / `buf_data[i]` word is **Q17.14** as `carry_save_streaming_contract.md`
§4 specifies — the shim, not the wire, is where fp32/int32 becomes fixed point.
`M_AXIS_CS` framing, `TID` / `TUSER`, and the `buf_full` / `buf_clear` record
semantics are unchanged from contract §6.

---

## 6. Required build configuration

Shipped `VX_config.toml` runs the TCU **off** and at toy dimensions. An
integration build sets, at minimum:

| Flag | Shipped | Integration | Note |
|------|---------|-------------|------|
| `VX_CFG_EXT_TCU_ENABLE` | `false` | **`true`** | enables the tensor ISA extension + `VX_tcu_unit` in `VX_execute` |
| `VX_CFG_TCU_TYPE` | `"TFR"` | `"TFR"` | keep — Ten-Four native path |
| `VX_CFG_NUM_THREADS` | `4` | ≥ `8` (real) | drives `NUM_TCU_LANES` and the `e` count; tap shape is invariant to it |
| `VX_CFG_TCU_FP8_ENABLE` | `false` | `true` | FP8 inference regime |
| `VX_CFG_TCU_INT8_ENABLE` | `false` | `true` | INT8 inference regime (exact shim path, §5.1) |
| `VX_CFG_TCU_MX_ENABLE` | `false` | optional | on → hardware microscale exponent for §5.2; off → shim self-derives |
| `VX_CFG_TCU_USE_DSP` | `1` on FPGA synth | `1` | FEDP mantissa multipliers → DSP48; matters for our U55C timing budget |
| `VX_CFG_NUM_TCU_BLOCKS` | `= ISSUE_WIDTH` | `= ISSUE_WIDTH` | one `VX_tcu_core` (one tap) per block |
| `VX_CFG_TCU_WGMMA_ENABLE` | `false` | evaluate | on → hardware K-stepping + `is_last_uop`; simplifies §8 tile-final filtering but adds an LMEM read port |

`VX_CFG_MISA_EXT` (`VX_config.toml:421`) already folds
`VX_CFG_EXT_TCU_ENABLED << 9` into MISA, so software feature-detects the unit
once the flag is set.

---

## 7. What does NOT need touching

- **Carry-save resolution** — done inside `tfr/VX_tcu_tfr_acc.sv` + `norm_round`;
  the tap gets a resolved 32-bit scalar. No change to Vortex's reduction.
- **Backpressure** — `VX_tcu_core` already has a LUTRAM landing queue
  (`:729-746`) that parks completed results behind a stalled consumer. The
  pilot's per-lane async FIFO `TREADY` wires to `result_if.ready`; that landing
  queue is free upstream slack.
- **Register writeback path** — `VX_lane_gather` → `commit_if` → scoreboard is
  untouched; the `M_AXIS_CS` tap is a fanout, not a diversion. The MMA result
  still commits to the RF as normal (the optical reduction consumes a copy).

---

## 8. Tile-final marker: determination and check

Contract §6.2 ("one beat = one reduction") requires `M_AXIS_CS` to carry **only
the fully-accumulated C tile**, not every K-step. Determination below is
source-verified; the check is what the integration team runs against its own
`VX_CFG_*` before trusting the shim.

### 8.1 Determination — there is no ready-made marker; use `step_k`

`VX_tcu_core.result_if` fires **once per compute uop** — `fedp_enqueue =
execute_fire && !is_wgmma_setup` (`VX_tcu_core.sv:148`), `mdata_push =
fedp_enqueue` (`:257`), `fedp_delay_pipe` shifts one bit per uop (`:220-229`). A
single `INST_TCU_WMMA` expands to `TCU_UOPS = TCU_M_STEPS · TCU_N_STEPS ·
TCU_K_STEPS` uops (`VX_tcu_pkg.sv:171`; `uop_count = TCU_UOPS`,
`VX_tcu_uops.sv:232`), so one instruction produces `TCU_UOPS` result beats.

Candidate markers, all rejected:

| Candidate | Verdict | Evidence |
|-----------|---------|----------|
| `header.sop` / `header.eop` | **Not tile-final.** Generic execute-pipeline SIMD-packet start/end flags; `mdata_queue_in = execute_if.data.header` passes them straight through (`VX_tcu_core.sv:156`). They mark SIMD sub-packet boundaries, unrelated to K-stepping. | `VX_define.vh:573-587` (`sop`/`eop` in the generic header); `VX_tcu_core.sv:156,277` |
| `op_args.tcu.is_last_uop` | **WGMMA-only and insufficient.** Assigned only inside `if (is_wgmma)` (`VX_tcu_uops.sv:419-427`); never set for plain WMMA. Even under WGMMA it flags only `uop_idx == uop_count-1` — the *single* last (m,n) sub-tile at last-k, not every sub-tile's last-k. Also not carried on `result_if` (only the header rides `mdata_queue`, not `op_args`). | `VX_tcu_uops.sv:421-426`; `VX_tcu_core.sv:154-156,277` |
| `fu_unlock` | WGMMA lockstep release, same single-uop limitation as `is_last_uop`. | `VX_tcu_uops.sv:422` |

**The usable primitive is `step_k`.** Every uop (WMMA and WGMMA) carries
`op_args.tcu.step_k = 4'(k_index)` (`VX_tcu_uops.sv:396,408`), visible in the core
as `wire [3:0] step_k = execute_if.data.op_args.tcu.step_k` (`VX_tcu_core.sv:136`,
currently `UNUSED_VAR` at `:159`). Loop order is **K-outermost** — non-WGMMA
`k_index = eff_ctr[LG_N+LG_M +: LG_K]` (`VX_tcu_uops.sv:268`); WGMMA dense is
"m inner → n middle → k outer" (`VX_tcu_uops.sv:174`). So the last
`TCU_M_STEPS · TCU_N_STEPS` uops of an instruction all have `step_k` at its max,
one per (m,n) sub-tile, each the final accumulate for that sub-tile's C
registers. The tile-final condition is:

```
is_tile_final = (step_k == BLOCK_K_STEPS - 1)
  where BLOCK_K_STEPS = is_wgmma ? TCU_WG_K_STEPS : TCU_K_STEPS
```

### 8.2 Elaborated numbers — shipped `VX_config.toml` (`NUM_THREADS = 4`)

| Param | Value | Source |
|-------|-------|--------|
| `TCU_NT`, `TCU_NR` | 4, 8 | `VX_tcu_pkg.sv:47,52` |
| `TCU_TILE_CAP` = NT·NR | 32 | `:57` |
| `TCU_TILE_M` / `TCU_TILE_N` | 8 / 4 | `:62-63` (EM=3, EN=2) |
| `TCU_TILE_K` = CAP / max(M,N) | 4 | `:64` |
| `TCU_TC_M` / `TCU_TC_N` / `TCU_TC_K` | 2 / 2 / 2 | `:72-74` (BLOCK_CAP=NT=4) |
| `TCU_M_STEPS` / `TCU_N_STEPS` / `TCU_K_STEPS` | 4 / 2 / 2 | `:77-79` |
| `TCU_UOPS` = M·N·K | **16** | `:171` |
| result beats per WMMA instr | **16** | one per uop |
| tile-final beats (`step_k==1`) | **8** (= M_STEPS·N_STEPS) | last 8 uops |

A real integration build (larger `NUM_THREADS`, FP8/INT8 on) changes every
number; re-derive `BLOCK_K_STEPS` from the elaborated package and feed it to the
check.

### 8.3 The RTL hook (shim side, in the Vortex tree)

`step_k` is not currently piped past the FEDP latency. Draft reference
implementation: **`gcb-rtl/integration/VX_tcu_tilefinal_tag.sv`** — an inline
wrapper placed around `VX_tcu_core` in `VX_tcu_unit`'s `g_blocks` loop
(`execute_if` / `result_if` face `VX_tcu_unit`; `execute_core_if` /
`result_core_if` face the wrapped core). It:

1. snoops the execute side and reconstructs the core's own predicates —
   `tag_bit_in = (step_k == k_last)` with
   `k_last = is_wgmma ? K_LAST_WG : K_LAST_NONWG`, and
   `tag_push = exe_fire && ~is_setup` (= `VX_tcu_core` `fedp_enqueue`,
   `VX_tcu_core.sv:148`);
2. reconstructs `setup_valid_r` (`VX_tcu_core.sv:206-218`) so it pops on exactly
   `fedp_result_fire` (`:204`), and pushes the 1-bit tag into a **mirror FIFO of
   the same depth and `OUT_REG` as `mdata_queue`** (`TAG_QUEUE_DEPTH =
   1 << clog2(VX_CFG_TCU_LATENCY + 1)`) — so the tag head tracks
   `result_if.data.header` beat-for-beat, covering both the direct-`fedp_done`
   and landing-queue-parked paths without replicating `fedp_delay_pipe`;
3. drives `is_tile_final` (aligned to `result_if.valid`); setup-uop result beats
   force it to 0 and neither push nor pop the tag FIFO;
4. the shim then sets `M_AXIS_CS.TVALID = result_if.valid && is_tile_final`;
   non-final beats are consumed (`result_if.ready` held high) but not streamed —
   the RF still gets every writeback.

Carries `SIMULATION` assertions mirroring §8.4 (empty-FIFO-on-compute-beat,
overflow, an optional `header.eop != is_tile_final` regression latch under
`VX_TCU_TILEFINAL_EOP_GUARD`, and a `TCU_K_STEPS==1` degenerate-case note).

### 8.4 The check — run against the integration config

**SVA (bind into `VX_tcu_core`), per accepted WMMA instruction:**

```systemverilog
// A1: result_if fires exactly TCU_UOPS times between one execute_fire of a
//     new uuid and the next (no coalescing, no extra beats).
// A2: exactly TCU_M_STEPS*TCU_N_STEPS of those beats have step_k == K_STEPS-1.
// A3: is_tile_final (8.3) is high on exactly those beats and nowhere else.
// A4: for every (step_m,step_n) pair, the beat with step_k==K_STEPS-1 is the
//     LAST result beat carrying that (step_m,step_n) in the instruction
//     (i.e. it is the final accumulator writeback for that sub-tile).
// A5: header.eop must NOT be equal to is_tile_final on every beat
//     (regression guard: if a future rebase repurposes eop, this fires).
property p_tilefinal_count;
  @(posedge clk) disable iff (reset)
  (new_instr |-> ##[1:$] (beats_seen == TCU_UOPS && tf_seen == M_STEPS*N_STEPS));
endproperty
assert property (p_tilefinal_count);
```

**Directed test (C or driver):** issue a single `wmma` with A, B, C set so the
exact integer result per (m,n) is known (e.g. A = all-ones INT8, B = identity,
C = 0 → D[m][n] = TILE_K). Capture `M_AXIS_CS`; assert:

1. beat count on the stream = `M_STEPS·N_STEPS` (tile-final only), **not**
   `TCU_UOPS`;
2. each streamed `acc_word`, de-scaled, equals the known D[m][n];
3. no beat carries a partial (`step_k < K_STEPS-1`) value — cross-check against a
   second run that taps raw `result_if` and counts `TCU_UOPS` beats.

**Config sweep:** run the SVA build for `{WGMMA off, WGMMA on}` ×
`{NUM_THREADS = 8, 16}` × `{FP8, INT8}` and confirm `BLOCK_K_STEPS` and the
`tf_seen` count track the elaborated package each time. If `TCU_K_STEPS == 1`
for a chosen config (TILE_K == TC_K), **every** uop is tile-final and the marker
degenerates to `!is_wgmma_setup` — valid, but note it so the shim isn't
"filtering" nothing.

**Implementation (`gcb-rtl/integration/`):**
- `tcu_tfr_config.sh` — the `VX_CFG_*` target: `VX_CFG_XLEN=32`,
  `VX_CFG_EXT_TCU_ENABLE`, `VX_CFG_TCU_TYPE=TFR`, `VX_CFG_TCU_USE_DSP=1`,
  `VX_CFG_NUM_THREADS`, FP8/INT8, optional WGMMA; sweep via `VX_TFR_THREADS` /
  `VX_TFR_FMT` / `VX_TFR_WGMMA` / `VX_TFR_XLEN`.
- `VX_tcu_tilefinal_sva.sv` — A1–A5 checker module (authored from the §8 source
  cites). `VX_tcu_tilefinal_sva_bind.sv` binds it into every `VX_tcu_core`,
  kept out of the vortex tree.
- `tb/sim_main.cpp` — Verilator `--exe` driver: reset `VX_tcu_unit_top`, one
  `INST_TCU_WMMA` dispatch, wait for commit; the bound SVA runs A1–A5 during it.
- `tb/run_tilefinal_check.sh` — stages: 0 `gen_config` (resolve + emit
  `VX_config.vh`/`VX_types.vh`), 1 SVA standalone lint, 2 tag-wrapper standalone
  lint (PARTIAL), 3 `verilator --binary` of `VX_tcu_unit_top` + the bound SVA,
  runs one WMMA. Stages 0/1/3 green on Verilator 5.032 + the `vortex` clone;
  exits 2 (SKIP) without them. Wired into `tb/ci.sh` as `tilefinal-sva`.
  **TODO:** the directed A=all-ones INT8 / B=identity / C=0 case + `M_AXIS_CS`
  capture + the `{8,16}×{FP8,INT8}×{WGMMA}` sweep.

### 8.5 Result feeds back to the contract

`carry_save_streaming_contract.md` §9 "tile-final marker" bullet and §8 shim
item are updated to name `step_k == BLOCK_K_STEPS-1` (not `header.eop`, not
`is_last_uop`) as the derivation, with this section as the reference.

---

## 9. Other open items to confirm on the integration config

1. **Per-block vs per-SM stream.** `result_if` is per `VX_tcu_core` (per issue
   slot). For an N-unit optical cell we need N such taps routed to N lane FIFOs —
   confirm the cluster wiring (`VX_socket.sv` / `VX_cluster.sv`) exposes them or
   add a small egress arbiter. This **resolves the contract §9 "shared vs
   per-unit" open question toward per-block.**
2. **`NUM_TCU_LANES` vs optical lane count.** `data[]` has `NUM_TCU_LANES`
   (= `NUM_THREADS`) words; the 8-input optical cell wants 8. Map thread-lane →
   optical-lane explicitly (identity if `NUM_THREADS = 8`).
3. **Q17.14 integer range** (contract §9) — check the largest FP8/INT8 tile sum
   Vortex accumulates before a reduction against ±65 535; widen to Q19.12 if
   exceeded.
4. **MX combine rule.** If `VX_CFG_TCU_MX_ENABLE` is used, pin down how
   `sf_a[row]` and `sf_b[col]` compose into the per-PE block exponent (add vs
   max) against `VX_tcu_mx_scale.sv` semantics.
