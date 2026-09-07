# SPICE environment — ngspice + BSIM-CMG + ASAP7 (GCB single-slope readout)

One command to build or verify everything:

```bash
bash gcb-spec/scripts/setup_spice_env.sh          # build/fetch what is missing (idempotent)
bash gcb-spec/scripts/setup_spice_env.sh --check  # verify only
eval "$(bash gcb-spec/scripts/setup_spice_env.sh --env)"   # load env into the shell
```

Runs on **WSL2 Ubuntu with no root / no sudo**. Every step is idempotent — it
checks for its output artifact and skips if present, so re-running is cheap.

---

## Why a custom build

| tool | stock availability | verdict |
|---|---|---|
| Debian `ngspice` 45.2 | apt (`universe`) | **no BSIM-CMG (level 72)**, **no OSDI** — supported MOS levels 1-6,8-10,14,49,54-58,60,68,73 |
| conda-forge `ngspice` 41 | micromamba | same — no level 72, no OSDI |
| Xyce | — | not packaged for this distro; source build pulls Trilinos (hours) |

So the FinFET model is loaded at runtime through **OSDI** (Open Source Device
Interface): a self-built ngspice with `--enable-osdi`, plus BSIM-CMG compiled
from Verilog-A with OpenVAF.

---

## Components the script installs (all under `$HOME`, no root)

| component | source | landed at |
|---|---|---|
| build tools (bison, flex, autotools) | `micromamba` env, conda-forge | `$HOME/mm/bt` |
| **ngspice 44** | `git.code.sf.net/p/ngspice/ngspice` branch `ngspice-44`, `./configure --with-x=no --disable-debug --enable-osdi --without-readline --enable-openmp` | `$HOME/opt/ngspice/bin/ngspice` |
| **OpenVAF 23.5.0** | prebuilt static linux-amd64 (`openva.fra1.cdn.digitaloceanspaces.com`) | `$HOME/openvaf/openvaf` |
| **BSIM-CMG 111** Verilog-A | `github.com/dwarning/VA-Models` `code/bsimcmg/vacode111/bsimcmg.va` | compiled to `$HOME/gcb_spice/tb/bsimcmg.osdi` (module `bsimcmg_va`) |
| **ASAP7 PDK r1p7** | `github.com/The-OpenROAD-Project/asap7` submodule `asap7_pdk_r1p7` | `$HOME/pdk/asap7/.../models/hspice/7nm_{TT,SS,FF}.pm` |

## Path map produced by the script

```
$HOME/opt/ngspice/bin/ngspice          # simulator  (export GCB_NG)
$HOME/gcb_spice/tb/                     # working dir for decks  (export GCB_SPICE_TB)
    bsimcmg.osdi                        #   OSDI FinFET model  (lowercase relative name)
    7nm_{tt,ss,ff}_osdi.pm             #   ASAP7 cards, OSDI-transformed  (regenerated each run)
    smoke2.cir                          #   ASAP7 NMOS Id-Vg sanity
$HOME/pdk/asap7/asap7_pdk_r1p7/models/hspice/   # ASAP7 source cards  (export GCB_PDK_HSPICE)
```

## ASAP7 → OSDI card transform (step 5 of the script)

```
.model <name> nmos level = 72   →   .model <name> bsimcmg_va type=1
.model <name> pmos level = 72   →   .model <name> bsimcmg_va type=0
```

ngspice then warns and ignores `version, coremod, capmod, nseg` — parameters not
present in the OpenVAF build of CMG 111. Immaterial for DC / transient
large-signal + thermal work. **Not** re-calibrating; just dropping unknown keys.

## ngspice / OSDI gotchas (baked into the decks)

1. **OSDI instances use the `N` device prefix** — not `M` (built-in MOS) or `P`.
   `NN1 d g s b nmos_slvt nfin=7 l=21n`.
2. **`pre_osdi bsimcmg.osdi` goes inside the `.control` block**, before `run`/`dc`/`tran`.
   The `.model` type (`bsimcmg_va`) is resolved at analysis time, after `pre_osdi`.
3. **ngspice lowercases netlist lines** → keep the `.osdi` and `.pm` as lowercase
   relative names and run ngspice from `$GCB_SPICE_TB`.
4. A benign `.meas ... out of interval` makes ngspice exit non-zero — judge batch
   runs by their printed output, not `$?` (the `--check` path does this).
5. ASAP7 ships **no noise and no statistical/mismatch parameters** — flicker
   (`K_f`) and Pelgrom (`A_VT`) must come from literature proxies (see
   `gcb-papers/data/readout/spice/SPICE_RESULTS*.md`).

## Run recipe

```bash
eval "$(bash gcb-spec/scripts/setup_spice_env.sh --env)"
cd "$GCB_SPICE_TB"

# ASAP7 device sanity
ngs smoke2.cir

# ramp generator, one corner (see models/readout/spice/tb/ramp_v2*.cir)
sed -e 's/MODELFILE/7nm_ss_osdi.pm/' ramp_v2.cir | \
  sed 's/^.control/.options temp=125\n.control/' > _run.cir
ngs _run.cir

# INL extraction + MC feedback: gcb-spec/models/readout/spice/harness/
python3 harness/ramp_inl_extract.py     # -> gcb-papers/data/readout/ramp_inl/*.csv
```

## Reproduce a clean machine

`setup_spice_env.sh` with no args does the full chain end-to-end (~6 min: most of
it is the ngspice `make -j`). Network is required for the git clones and the
OpenVAF binary. Disk footprint ≈ 1.5 GB (ngspice build tree + ASAP7 + VA-Models).
