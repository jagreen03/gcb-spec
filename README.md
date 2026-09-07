# gcb-spec

Single source of truth: MMIO register map, architecture log, ADRs

Part of the GreenCoyote-Bay photonic inference fabric (ODIN_Bridge).

## AI Onboarding (Paved Road)

**New AI agent working on GCB: read
[`ai-agents/README.md`](ai-agents/README.md) first and adopt your designated
persona before doing anything else.**

Context is expensive to rebuild every session and that is where drift and
hallucination start. `ai-agents/` holds three role-specific system prompts —
**System Architect**, **Analog / Spec Evaluator**, **RTL / Quality Verifier** —
each carrying the current *Single-Slope CONDITIONAL GO* state compression and a
strictly isolated set of rules. Pick the one that matches your task, paste it as
your system prompt, and stay in that lane. Do not operate un-personalised.

## Contents

- `ai-agents/` — role-specific AI initialization prompts (the paved road); start
  at [`ai-agents/README.md`](ai-agents/README.md)
- `registers.yaml` / `regen.py` — MMIO register map and code generation
- `architecture.md` — architectural log
- `bench_emulation_parameters.md` — Task 3 discrete reduction-cell component
  parameters, tied to `gcb-rtl/sim/mmi_tree_model.py`
- `carry_save_streaming_contract.md` — logical streaming contract for the Vortex
  3.0 accumulator → optical pilot boundary (`buf_data` / `buf_full` format, AXI
  4-Stream handshake, block-floating-point 32→12-bit scaling)
- `vortex_integration_notes.md` — compute-side tap, source-verified against the
  cloned Vortex 3.0 tree: `VX_tcu_core.result_if` writeback, `tcu_result_t`
  layout, fp32/int32 → Q17.14 shim, required `VX_CFG_*` build flags
- `docs/adr/` — ADRs (ADR-001, ADR-005; 002–004 reserved/unfiled)
- `concepts/` — AI-generated concept renders of the *planned* hardware form
  factor. **Concept art, not photographs or CAD** — see
  [`concepts/README.md`](concepts/README.md) for the full caveat.

