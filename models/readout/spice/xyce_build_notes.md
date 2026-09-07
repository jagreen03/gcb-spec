# Xyce build attempt (blocked)

Goal: native BSIM-CMG transient noise, no OSDI.

Steps taken:
  micromamba create -p ~/mm/xyce -c conda-forge trilinos cmake openmpi       openblas fftw suitesparse gcc gxx gfortran flex bison
  git clone -b Release-7.10.0 https://github.com/Xyce/Xyce.git
  # patch cmake/tps.cmake: replace
  #   find_package(Trilinos CONFIG REQUIRED <components>)
  # with
  #   find_package(Trilinos CONFIG REQUIRED)
  #   + alias every <pkg>::all_libs onto Trilinos::all_libs
  cmake -D Trilinos_ROOT=~/mm/xyce -D Xyce_PARALLEL_MPI=OFF ...

Blocker: conda-forge Trilinos 16.2.0 is a stripped/other-consumer build:
  - NOX built WITHOUT LOCA          (Xyce needs LOCA)
  - EpetraExt built WITHOUT BTF     (Xyce needs BTF)
  - LAPACK not exposed via Trilinos
  - only Trilinos::all_libs / Kokkos::all_libs targets exist (no per-package)
  - dangling PyTrilinos::all_libs in the link interface
  - no Isorropia / Zoltan targets (needed for MPI builds)

A from-source Trilinos with Xyce reference config (~2 h, no root, high API-drift
risk vs Trilinos 16.2) was out of scope.  Fell back to ngspice .noise on a
gm-matched BSIM4 diff pair -- see SPICE_RESULTS_V3.md sec 7.
