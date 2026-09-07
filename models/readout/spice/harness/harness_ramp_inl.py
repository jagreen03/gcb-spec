#!/usr/bin/env python3
"""
Run the discharge-mode cascode ramp (ramp_v2.cir) across the 9 ASAP7 PVT
corners; extract each corner's measured INL curve; export CSV (u, delta),
>=128 rows, for ss_readout_mc.py's ramp_inl_file.

u     = code / time fraction across the used ramp window (u=0 at window top /
        ramp start, u=1 at the floor).  Counter counts uniform clock ticks, so
        the code axis is uniform TIME.
delta = (v_ramp_measured(u) - ideal_linear_ramp(u)) / ramp_range
        i.e. how far the real ramp voltage is from a straight line in time,
        as a fraction of the window range.  This is exactly the perturbation
        ss_readout_mc.py applies as `u = u + interp(u, uu, dd)`.

Per corner also: slope (mV/ns), INL rms/max (% of FS),
  D = RMS(delta_corner - delta_TT27) / RMS(delta_TT27)   (shape-drift vs TT/27).
"""
import os, subprocess, json, numpy as np

TB   = os.path.expanduser("~/gcb_spice/tb")
NG   = os.path.expanduser("~/opt/ngspice/bin/ngspice")
OUTD = "/mnt/d/R/S/H/gcb-papers/data/readout/ramp_inl"
FS_V = 0.5683
WIN  = (0.200, 0.720)             # used ramp window [floor, top]
NROWS = 129
CORNERS = [(m, T) for m in ("tt", "ss", "ff") for T in (-40, 27, 125)]
os.makedirs(OUTD, exist_ok=True)


def run_corner(model_file, tempC, tag):
    deck = open(f"{TB}/ramp_v2.cir").read()
    deck = deck.replace("MODELFILE", model_file).replace("OUTFILE", f"_ri_{tag}.txt")
    deck = deck.replace(".control\npre_osdi", f".options temp={tempC}\n.control\npre_osdi")
    open(f"{TB}/_ri_{tag}.cir", "w").write(deck)
    subprocess.run([NG, "-b", f"_ri_{tag}.cir"], cwd=TB, capture_output=True, text=True, timeout=600)
    rows = []
    for ln in open(f"{TB}/_ri_{tag}.txt"):
        s = ln.split()
        if len(s) < 2:
            continue
        try:
            rows.append((float(s[0]), float(s[1])))
        except ValueError:
            pass
    t = np.array([r[0] for r in rows]); v = np.array([r[1] for r in rows])
    order = np.argsort(t); t, v = t[order], v[order]
    # keep the strictly-falling segment inside the window
    m = (v >= WIN[0]) & (v <= WIN[1])
    t, v = t[m], v[m]
    keep = np.concatenate(([True], np.diff(v) < 0))   # drop non-decreasing points
    t, v = t[keep], v[keep]
    rng = WIN[1] - WIN[0]
    uu = (t - t[0]) / (t[-1] - t[0])                  # uniform-time / code fraction
    c = np.polyfit(uu, v, 1)                          # best-fit straight line in time
    delta_w = (v - np.polyval(c, uu)) / rng
    ug = np.linspace(0.0, 1.0, NROWS)
    dg = np.interp(ug, uu, delta_w)
    slope = abs(c[0]) / (t[-1] - t[0]) * (t[-1] - t[0])   # = |c[0]| per unit u
    slope_mv_ns = abs(np.polyfit(t, v, 1)[0]) / 1e6
    inl_rms = float(np.sqrt(np.mean(dg ** 2)) * rng / FS_V * 100)
    inl_max = float(np.max(np.abs(dg)) * rng / FS_V * 100)
    return ug, dg, dict(model=model_file, tempC=tempC, slope_mV_ns=round(slope_mv_ns, 3),
                        INL_rms_pctFS=round(inl_rms, 4), INL_max_pctFS=round(inl_max, 4),
                        window_V=list(WIN), n_rows=NROWS)


def main():
    curves, meta = {}, {}
    for m, T in CORNERS:
        tag = f"{m}_{T}"
        u, d, info = run_corner(f"7nm_{m}_osdi.pm", T, tag)
        curves[tag] = (u, d); meta[tag] = info
        p = f"{OUTD}/ramp_inl_{tag}.csv"
        with open(p, "w") as f:
            f.write(f"# u,delta -- ASAP7 {m.upper()}/{T}C discharge-mode cascode ramp INL ; "
                    f"delta=(v-linfit_in_time)/range ; V_FS={FS_V} V ; window {WIN} V ; {NROWS} rows\n")
            f.write("# columns: u,delta\n")
            for uu, dd in zip(u, d):
                f.write(f"{uu:.6f},{dd:.8e}\n")
        info["csv"] = p
        print(f"{tag:8s} slope {info['slope_mV_ns']:6.3f} mV/ns  "
              f"INL rms {info['INL_rms_pctFS']:.4f}%  max {info['INL_max_pctFS']:.4f}%")
    ur, dr = curves["tt_27"]
    ref = float(np.sqrt(np.mean(dr ** 2)))
    print("\nshape-drift D vs TT/27  (RMS(delta_corner - delta_TT27)/RMS(delta_TT27)):")
    for tag, (u, d) in curves.items():
        D = float(np.sqrt(np.mean((d - dr) ** 2)) / ref) if ref > 0 else 0.0
        meta[tag]["D_vs_TT27"] = round(D, 4)
        print(f"  {tag:8s} D = {D:.4f}")
    json.dump(meta, open(f"{OUTD}/ramp_inl_meta.json", "w"), indent=2)
    print(f"\nwrote {OUTD}/ramp_inl_meta.json  and 9 CSVs in {OUTD}")


if __name__ == "__main__":
    main()
