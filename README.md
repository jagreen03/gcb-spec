# gcb-spec

Single source of truth: MMIO register map, architecture log, ADRs

Part of the GreenCoyote-Bay photonic inference fabric (ODIN_Bridge).

## Contents

- `registers.yaml` / `regen.py` — MMIO register map and code generation
- `architecture.md` — architectural log
- `bench_emulation_parameters.md` — Task 3 discrete reduction-cell component
  parameters, tied to `gcb-rtl/sim/mmi_tree_model.py`
- `carry_save_streaming_contract.md` — logical streaming contract for the Vortex
  3.0 accumulator → optical pilot boundary (`buf_data` / `buf_full` format, AXI
  4-Stream handshake, block-floating-point 32→12-bit scaling)
- `decisions/` — ADRs
- `concepts/` — AI-generated concept renders of the *planned* hardware form
  factor. **Concept art, not photographs or CAD** — see
  [`concepts/README.md`](concepts/README.md) for the full caveat.

