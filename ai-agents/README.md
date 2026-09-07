# GCB AI Agent Prompts — the Paved Road

This directory holds **role-specific initialization prompts**. Each file is
written to be pasted verbatim as the **System Prompt** (or the first message) of
a new AI session working on GreenCoyote-Bay.

## Why this exists

Every fresh AI session was re-deriving the same context — the readout verdict,
the SPICE numbers, the timing budget, the register-map rules — from scratch.
That is expensive and it is where drift and hallucination creep in ("let's just
add gain in the integrator", "ripple carry is simpler", "re-open the
sigma-delta idea"). These prompts pave the road: they load the hard-won state
once, fix the role's boundaries, and list the things that must never be
forgotten or silently changed.

## The triad

| File | Persona | Owns | Must not touch |
|---|---|---|---|
| [`AGENT_01_SYSTEM_ARCHITECT.md`](AGENT_01_SYSTEM_ARCHITECT.md) | **System Architect** | Macro-architecture, Vortex RISC-V ISA tap, DMA / carry-save streaming, MMIO usability, Von Neumann starvation | Analog physics, SPICE, device noise, ramp/comparator design, RTL timing |
| [`AGENT_02_ANALOG_EVALUATOR.md`](AGENT_02_ANALOG_EVALUATOR.md) | **Analog / Spec Evaluator** | Deep-submicron physics, SPICE, transient noise, `V = Q/C`, the CONDITIONAL GO boundary, spec limits | ISA / DMA design, RTL, toggle counts, SystemVerilog timing |
| [`AGENT_03_RTL_VERIFIER.md`](AGENT_03_RTL_VERIFIER.md) | **RTL / Quality Verifier** | Bit-exact verification, SystemVerilog, static-CMOS timing closure, energy from toggle counts, `regen.py` discipline, DD-001 | Analog noise numbers, physics, macro-architecture scope |

## How to use

1. Decide which role the task belongs to. If it spans two, it is two sessions.
2. Open the matching file. Paste **everything from the `--- SYSTEM PROMPT ---`
   line onward** into the new session as the system prompt.
3. State your task. The agent will stay in role and will refuse — and tell you
   which sibling agent owns it — if the task crosses its boundary.

Do **not** merge two personas into one session to "save time". The isolation is
the point: a single agent that is allowed to move both the analog spec and the
RTL will eventually trade one against the other without noticing.

## Shared invariants (all three enforce these)

- **No silicon exists.** Every quantity is a simulation, model, or
  bit-exact-verification output. Say so.
- **Verdict: CONDITIONAL GO.** Do not promote to GO without the standing
  commercial transient-noise histogram (Cadence Spectre / native BSIM-CMG). Do
  not demote without new evidence.
- **ADR-005 is locked.** The receiver is a single-slope CIS readout. The
  charge-balancing sigma-delta and the tail-injection ICO branches are
  **retired** — no free oversampling, every sub-block re-adds the cost they
  claim to remove. Do not re-open without new physics.
- **`registers.yaml` is a source, not an artifact.** It is edited only through
  `regen.py`, which regenerates five consumers (gcb-rtl SV, gcb-host hpp + py,
  gcb-dashboard ts, gcb-wiki datasheet md). Never hand-edit a generated view.
- **DD-001:** the shared 6 GHz Gray counter is carry-select / carry-lookahead,
  never ripple carry.
- **Repo set:** six repos (`gcb-spec`, `gcb-rtl`, `gcb-host`, `gcb-dashboard`,
  `gcb-papers`, `gcb-wiki`), all tagged `v0.1`, all on `main`, synced with
  origin as of 2026-09-07.

## Maintenance

When the verdict, a gate number, or a design decision changes, update the
`## GCB STATE COMPRESSION` block **in all three agent files** and in
`gcb-spec/GCB_STATE_COMPRESSION.txt`, and bump the date. The blocks are
duplicated on purpose — each agent prompt must stand alone.
