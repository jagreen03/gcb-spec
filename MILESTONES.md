# GCB Milestones

Release milestones for the GreenCoyote-Bay fabric. Milestones are coordinated
across all six repos (`gcb-spec`, `gcb-rtl`, `gcb-host`, `gcb-dashboard`,
`gcb-papers`, `gcb-wiki`) — one annotated tag and one GitHub release per repo
per milestone. Milestone drafts live in
[`docs/milestones/`](docs/milestones/).

| Milestone | Scope | Status | Detail |
|---|---|---|---|
| **v0.1** | Coordinated **CONDITIONAL GO** snapshot of the single-slope readout — source of truth, verified RTL, ramp characterised over 9 PVT corners, preprint + preliminary datasheet, AI-onboarding triad. | **Released** 2026-09-07 (tags `v0.1` on all six repos; `v0.1.1` on `gcb-spec` adds `ai-agents/`). | GitHub release per repo; PDFs attached to the `gcb-papers` `v0.1` release. |
| **v0.2** | **Spectre transient-noise closure** — replace the BSIM4 `.noise` surrogate (53 µV, ±16 % band straddling the 55 µV gate) with a commercial transient-noise histogram on a native FinFET model, moving the readout verdict **CONDITIONAL GO → GO** (or executing the gm-C first-stage fallback and re-gating). | **DRAFT / not started.** | [`docs/milestones/v0.2-spectre-noise-closure.md`](docs/milestones/v0.2-spectre-noise-closure.md) |

## Current standing item (blocks v0.2 → done)

A transient-noise histogram of the comparator decision at the 4.2 mV/ns ramp
crossing on Cadence Spectre (or AFS) with native BSIM-CMG, at the frozen v0.1
design point. **Met (→ GO)** when: measured σ ≤ 55 µV at the design point,
**and** the charge-domain Monte Carlo re-run at that σ over all 9 ramp-INL
corners gives worst-corner p05 ≥ 56 dB, **and** σ is within ±20 % of the 53 µV
surrogate. See the v0.2 draft for the full run matrix, contingencies, and
task checklist.
