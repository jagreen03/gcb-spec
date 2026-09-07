#!/usr/bin/env bash
# ============================================================================
# setup_spice_env.sh -- reproducible ngspice + BSIM-CMG + ASAP7 environment
# for the GCB single-slope readout transient proof.
#
# Target: WSL2 Ubuntu, NO root / NO sudo.
# Idempotent: every step checks for its artifact and skips if present.
# After a successful run it prints the env block to source for a session.
#
#   bash gcb-spec/scripts/setup_spice_env.sh          # build/fetch what's missing
#   bash gcb-spec/scripts/setup_spice_env.sh --check  # verify only, no build
#   bash gcb-spec/scripts/setup_spice_env.sh --env    # just print the env block
# ============================================================================
set -euo pipefail

PREFIX="${GCB_SPICE_PREFIX:-$HOME/opt/ngspice}"
WORK="${GCB_SPICE_WORK:-$HOME/gcb_spice}"
MAMBA_ROOT="${MAMBA_ROOT_PREFIX:-$HOME/mm}"
NG_BRANCH="ngspice-44"
OPENVAF_URL="https://openva.fra1.cdn.digitaloceanspaces.com/openvaf_23_5_0_linux_amd64.tar.gz"
VA_MODELS="https://github.com/dwarning/VA-Models.git"
ASAP7_REPO="https://github.com/The-OpenROAD-Project/asap7.git"

NG="$PREFIX/bin/ngspice"
OSDI="$WORK/tb/bsimcmg.osdi"
PDK_HSPICE="$HOME/pdk/asap7/asap7_pdk_r1p7/models/hspice"
VACODE="$HOME/VA-Models/code/bsimcmg/vacode111/bsimcmg.va"

log(){ printf '\033[1;32m[setup]\033[0m %s\n' "$*"; }
err(){ printf '\033[1;31m[setup] ERROR:\033[0m %s\n' "$*" >&2; }

print_env(){
  cat <<EOF
# ---- source this for a SPICE session ----
export MAMBA_ROOT_PREFIX=$MAMBA_ROOT
export GCB_NG=$NG
export GCB_SPICE_TB=$WORK/tb
export GCB_PDK_HSPICE=$PDK_HSPICE
alias ngs='\$GCB_NG -b'
# decks live in \$GCB_SPICE_TB ; run from there so 'pre_osdi bsimcmg.osdi'
# and '.include 7nm_tt_osdi.pm' resolve as lowercase relative names.
EOF
}

check(){
  local ok=1
  [ -x "$NG" ]         && log "ngspice      OK  $($NG --version 2>&1 | grep -m1 ngspice- || true)" || { err "ngspice missing ($NG)"; ok=0; }
  [ -f "$OSDI" ]       && log "bsimcmg.osdi OK  $OSDI" || { err "OSDI model missing ($OSDI)"; ok=0; }
  [ -d "$PDK_HSPICE" ] && log "ASAP7 hspice OK  $PDK_HSPICE" || { err "ASAP7 models missing ($PDK_HSPICE)"; ok=0; }
  for c in tt ss ff; do
    [ -f "$WORK/tb/7nm_${c}_osdi.pm" ] && log "7nm_${c}_osdi.pm OK" || { err "OSDI-transformed card 7nm_${c}_osdi.pm missing"; ok=0; }
  done
  if [ "$ok" = 1 ] && [ -x "$NG" ] && [ -f "$WORK/tb/smoke2.cir" ]; then
    # ngspice can exit non-zero on a benign .meas out-of-interval; judge by output, not $?
    local so; so="$(cd "$WORK/tb" && "$NG" -b smoke2.cir 2>&1 || true)"
    if printf '%s' "$so" | grep -qE "id_on *=.*[0-9]" && printf '%s' "$so" | grep -qE "gm_max *=.*[0-9]"; then
      local idon; idon="$(printf '%s' "$so" | sed -n 's/.*id_on *= *\([0-9.eE+-]*\).*/\1/p' | head -1)"
      log "smoke        OK  (ASAP7 NMOS Id(Vgs=Vds=0.7,nfin=7)=${idon} A)"
    else
      err "smoke test failed"; ok=0
    fi
  fi
  return $((1-ok))
}

[ "${1:-}" = "--env" ]   && { print_env; exit 0; }
[ "${1:-}" = "--check" ] && { check && { log "environment READY"; exit 0; } || { err "environment INCOMPLETE"; exit 1; }; }

mkdir -p "$WORK/tb" "$WORK/out" "$HOME/bin" "$HOME/pdk"

# 1. micromamba (build-tool provider; no root) --------------------------------
if [ ! -x "$HOME/bin/micromamba" ]; then
  log "bootstrapping micromamba"
  curl -Ls -o /tmp/mm.tar.bz2 "https://micro.mamba.pm/api/micromamba/linux-64/latest"
  python3 -c "import bz2,tarfile,io,os;d=bz2.decompress(open('/tmp/mm.tar.bz2','rb').read());tarfile.open(fileobj=io.BytesIO(d)).extractall(os.path.expanduser('~'))"
  chmod +x "$HOME/bin/micromamba"
fi
export MAMBA_ROOT_PREFIX="$MAMBA_ROOT"
if [ ! -x "$MAMBA_ROOT/bt/bin/bison" ]; then
  log "creating build-tools env (bison flex autotools)"
  "$HOME/bin/micromamba" create -y -p "$MAMBA_ROOT/bt" -c conda-forge \
      bison flex make autoconf automake libtool pkg-config >/dev/null
fi
export PATH="$MAMBA_ROOT/bt/bin:$PATH"

# 2. ngspice-44 with OSDI ----------------------------------------------------
if [ ! -x "$NG" ]; then
  log "building ngspice $NG_BRANCH (--enable-osdi)"
  cd "$WORK"
  [ -d ngspice-git ] || git clone --depth 1 -b "$NG_BRANCH" https://git.code.sf.net/p/ngspice/ngspice ngspice-git
  cd ngspice-git && ./autogen.sh
  mkdir -p release && cd release
  ../configure --prefix="$PREFIX" --with-x=no --disable-debug --enable-osdi \
               --without-readline --enable-openmp CFLAGS="-O2 -w"
  make -j"$(nproc)" && make install
fi

# 3. OpenVAF + BSIM-CMG 111 -> OSDI ----------------------------------------
if [ ! -x "$HOME/openvaf/openvaf" ]; then
  log "fetching OpenVAF 23.5.0"
  mkdir -p "$HOME/openvaf" && cd "$HOME/openvaf"
  curl -fLs -o ov.tgz "$OPENVAF_URL"
  python3 -c "import tarfile;tarfile.open('ov.tgz').extractall()"
  chmod +x openvaf
fi
[ -d "$HOME/VA-Models" ] || { log "cloning VA-Models"; git clone --depth 1 "$VA_MODELS" "$HOME/VA-Models"; }
if [ ! -f "$OSDI" ]; then
  log "compiling bsimcmg.va -> bsimcmg.osdi"
  ( cd "$(dirname "$VACODE")" && "$HOME/openvaf/openvaf" bsimcmg.va )
  cp "$(dirname "$VACODE")/bsimcmg.osdi" "$OSDI"
fi

# 4. ASAP7 PDK r1p7 --------------------------------------------------------
if [ ! -d "$PDK_HSPICE" ]; then
  log "cloning ASAP7 + pdk submodule"
  cd "$HOME/pdk"
  [ -d asap7 ] || git clone --depth 1 "$ASAP7_REPO" asap7
  cd asap7 && git submodule update --init --depth 1 asap7_pdk_r1p7
fi

# 5. MAP: ASAP7 HSPICE cards -> OSDI-ready model cards --------------------
#    .model <n> nmos level=72  ->  .model <n> bsimcmg_va type=1   (type=0 pmos)
#    ngspice then ignores version/coremod/capmod/nseg (not in CMG 111) -- immaterial.
log "mapping ASAP7 model cards -> \$GCB_SPICE_TB/7nm_{tt,ss,ff}_osdi.pm"
for C in TT SS FF; do
  c=$(echo "$C" | tr '[:upper:]' '[:lower:]')
  awk '
    /^\.model[ \t]+[A-Za-z0-9_]+[ \t]+nmos[ \t]+level[ \t]*=[ \t]*72/ {sub(/nmos[ \t]+level[ \t]*=[ \t]*72/,"bsimcmg_va type=1");print;next}
    /^\.model[ \t]+[A-Za-z0-9_]+[ \t]+pmos[ \t]+level[ \t]*=[ \t]*72/ {sub(/pmos[ \t]+level[ \t]*=[ \t]*72/,"bsimcmg_va type=0");print;next}
    {print}
  ' "$PDK_HSPICE/7nm_${C}.pm" > "$WORK/tb/7nm_${c}_osdi.pm"
done

# 6. minimal smoke deck (kept in $WORK/tb) ------------------------------
cat > "$WORK/tb/smoke2.cir" <<'EOF'
* ASAP7 OSDI smoke -- NMOS Id-Vg via source branch current
.include 7nm_tt_osdi.pm
Vd d 0 0.7
Vg g 0 0
N1 d g 0 0 nmos_slvt nfin=7 l=21n
.control
pre_osdi bsimcmg.osdi
dc Vg 0 0.8 0.02
let id = -i(Vd)
let gm = deriv(id)
meas dc id_on  FIND id WHEN v(g)=0.7
meas dc gm_max MAX gm
.endc
.end
EOF

log "verifying"
check || { err "post-build verification FAILED"; exit 1; }
echo
log "environment READY"
print_env
