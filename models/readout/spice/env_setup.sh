#!/usr/bin/env bash
# Rebuild the ASAP7/OSDI/ngspice toolchain from nothing (no root). See README.md.
set -e
export MAMBA_ROOT_PREFIX=$HOME/mm
# 1. micromamba (bootstrap via python bz2 if no bzip2)
[ -x ~/bin/micromamba ] || { curl -Ls -o /tmp/mm.tar.bz2 https://micro.mamba.pm/api/micromamba/linux-64/latest; \
  python3 -c "import bz2,tarfile,io,os;d=bz2.decompress(open(\"/tmp/mm.tar.bz2\",\"rb\").read());tarfile.open(fileobj=io.BytesIO(d)).extractall(os.path.expanduser(\"~\"))"; chmod +x ~/bin/micromamba; }
# 2. build tools
~/bin/micromamba create -y -p $HOME/mm/bt -c conda-forge bison flex make autoconf automake libtool pkg-config
# 3. ngspice-44 + OSDI
cd ~/gcb_spice && git clone --depth 1 -b ngspice-44 https://git.code.sf.net/p/ngspice/ngspice ngspice-git || true
cd ngspice-git && PATH=$HOME/mm/bt/bin:$PATH ./autogen.sh && mkdir -p release && cd release
PATH=$HOME/mm/bt/bin:$PATH ../configure --prefix=$HOME/opt/ngspice --with-x=no --disable-debug --enable-osdi --without-readline --enable-openmp CFLAGS="-O2 -w"
PATH=$HOME/mm/bt/bin:$PATH make -j$(nproc) && make install
# 4. OpenVAF + BSIM-CMG
cd ~ && [ -x ~/openvaf/openvaf ] || { mkdir -p openvaf && cd openvaf && \
  curl -fLs -o ov.tar.gz https://openva.fra1.cdn.digitaloceanspaces.com/openvaf_23_5_0_linux_amd64.tar.gz && \
  python3 -c "import tarfile;tarfile.open(\"ov.tar.gz\").extractall()" && chmod +x openvaf; }
cd ~ && git clone --depth 1 https://github.com/dwarning/VA-Models.git || true
cd ~/VA-Models/code/bsimcmg/vacode111 && ~/openvaf/openvaf bsimcmg.va
cp bsimcmg.osdi ~/gcb_spice/tb/
# 5. ASAP7
cd ~ && mkdir -p pdk && cd pdk && git clone --depth 1 https://github.com/The-OpenROAD-Project/asap7.git || true
cd asap7 && git submodule update --init --depth 1 asap7_pdk_r1p7
echo "toolchain ready: $HOME/opt/ngspice/bin/ngspice"
