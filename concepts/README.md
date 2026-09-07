# GreenCoyote-Bay — Concept Renders

> [!WARNING]
> **These images are AI-generated concept art, not photographs.**
>
> Every picture in this folder was produced by an image-generation model from a
> text prompt. They depict **hypothetical, planned hardware** for the
> GreenCoyote-Bay (GCB / ODIN_Bridge) photonic inference fabric. Nothing here
> has been fabricated, bench-tested, or measured.
>
> - Not photographs of real boards.
> - Not manufacturing drawings, gerbers, or mechanical CAD.
> - Part numbers, silk-screen text, connector counts, and component placement
>   visible in the renders are **illustrative only** and are frequently wrong or
>   internally inconsistent (model artifacts).
> - Do **not** cite these as evidence that any GCB hardware exists, and do not
>   use them for BOM, layout, thermal, or signal-integrity work.
>
> The authoritative sources for GCB remain [`../registers.yaml`](../registers.yaml),
> [`../architecture.md`](../architecture.md), the ADRs in [`../docs/adr/`](../docs/adr/),
> and the RTL in the `gcb-rtl` repository.

## Purpose

These renders exist to give reviewers, collaborators, and documentation readers a
shared **mental picture** of the intended physical form factor: a modular,
card-based compute fabric on a passive PCIe backplane, with an off-board photonic
(Mach-Zehnder modulator) mesh reached over optical fiber. They are concept
imagery for slide decks and design discussion, nothing more.

## Index

| File | Concept it illustrates | Maps to |
|---|---|---|
| `images/GreenCoyote-Bay_MVU_4U_Chassis_Cutaway.png` | Full 4U "Modular Vector Unit" chassis: 8× PCIe Gen5 x16 passive backplane, GPU shard cards, FPGA/Versal card, EF100 CXL 3.0 switch card, GCB-MEM-1 CXL DRAM expander, 4+1 fans, dual 2700 W PSU, external MZM photonic module on fiber | System-level view of the whole fabric |
| `images/Passive_Fabric_Backplane.png` | Passive fabric backplane, 8× PCIe x16 slots, ATX 24-pin power in, power-distribution only (no active silicon) | "passive fabric" interconnect in `architecture.md` |
| `images/Xilinx_Versal_SoC_Card.png` | Versal adaptive SoC card acting as the **GCB proxy / host bridge**: PCIe Gen4 x8 edge, UART/JTAG header, AXI4 link out to the MZM mesh | `gcb-host` proxy role; `greencoyote_axi_lite_wrapper` / MMIO register interface |
| `images/MZM_Photonic_Mesh_Assembly.png` | Mach–Zehnder modulator photonic mesh assembly: driver array PCB over a photonic die, fiber ribbon breakout | Cascaded optical carry-save reduction fabric; `greencoyote_photonic_sequencer` |
| `images/GPU_Shard_Card_with_AOC.png` | Dual-fan "GPU shard" accelerator card with a QSFP-DD 800G active optical cable for card-to-card optical interconnect | RFI (Reduction Fabric Interface) interconnect paper; GPU-mode datapath (`is_14gpu_mode`, `buf_full[5:0]`) |
| `images/GCB-MEM-1_CXL_DRAM_Expander_Card.png` | CXL memory-expander card ("GCB-MEM-1, Zone B"): CXL controller ASIC plus DRAM array under a heatsink | Memory-expansion tier of the fabric |
| `images/Blueprint-RiverHorse_Program_Mark.png` | Program/word mark ("Blueprint.RiverHorse") — infinity loop + horse-head motif | Branding placeholder only; no technical content |

## Provenance

- Source dump: `D:\R\P\GCB\Pictures\` (as-found; imported read-only).
- `Blueprint-RiverHorse_Program_Mark.png` was present twice in the source
  (byte-identical, MD5 `680b01a2b5e525b02e53a64768b5f398`); one copy imported.
- Original generator/prompt metadata was not preserved with the files.
