#!/usr/bin/env python3
"""
Task 3 driver: run the ss_readout_mc.py (V2) design point against each of the 9
SPICE ramp-INL corner CSVs under 3 ramp conditions; collect median / p05 SNDR.

conditions
  c1  --set ramp_inl_reverse=1                                  charge-up polarity
  c2  --set ramp_inl_reverse=0                                  discharge-mode integrator
  c3  --set ramp_inl_reverse=0 --set ramp_lut_points=16
      --set ramp_shape_drift=D          D = per-corner INL-shape drift vs TT/27

design point (V2)
  ramp_dnl_sigma = 0        analog current-on-cap ramp (no DAC steps)
  v_comp_noise   = 50e-6    gate (a) thermal target (SPICE-open)
  v_comp_flicker = FLICK    gate (b): post-auto-zero residual from a published
                            7 nm FinFET K_F proxy.  default 50e-6 (AZ only);
                            15e-6 with an added chopper.  ASSUMED PROXY.
  v_comp_offset  = 5e-3     gate (c): raw input-pair sigma ~34 mV from A_VT =
                            2.0 mV.um (published FinFET proxy), divided by the
                            auto-zero loop gain (1+A_pre ~ 11) -> ~4-5 mV.
                            ASSUMED PROXY.
  calib 3pt, C_int 2 pF, n_bits 12, 4x6 GHz, --pvt (233/300/398 K)
"""
import json, os, subprocess, sys

PY     = os.environ.get("PY", r"D:/R/S/H/gcb-wdm-transceiver/.venv/Scripts/python.exe")
SCRIPT = r"D:/R/S/H/gcb-spec/models/readout/ss_readout_mc.py"
CSVDIR = r"D:/R/S/H/gcb-papers/data/readout/ramp_inl"
CSVWIN = r"D:/R/S/H/gcb-papers/data/readout/ramp_inl"
OUT    = r"D:/R/S/H/gcb-papers/data/readout/spice/mc_v2"
FLICK  = os.environ.get("FLICK", "50e-6")
NMC    = os.environ.get("NMC", "200")
OFFS   = os.environ.get("OFFS", "5e-3")
os.makedirs(OUT, exist_ok=True)

CORNERS = ["tt_-40", "tt_27", "tt_125", "ss_-40", "ss_27", "ss_125", "ff_-40", "ff_27", "ff_125"]
META = json.load(open(f"{CSVDIR}/ramp_inl_meta.json"))

DP = ["--set", "ramp_dnl_sigma=0", "--set", "v_comp_noise=50e-6",
      "--set", f"v_comp_flicker={FLICK}", "--set", f"v_comp_offset={OFFS}",
      "--calib", "3pt", "--n-mc", NMC, "--pvt"]


def run(csv_win, extra, jtag):
    jf = f"{OUT}/{jtag}.json"
    cmd = [PY, SCRIPT, *DP, "--set", f"ramp_inl_file={csv_win}", *extra, "--json", jf]
    subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    j = json.load(open(jf))
    s = j["results"]["sndr_crest_db"]
    pvt = j.get("pvt") or {}
    p05s = [s["p05"]] + [v["sndr_crest_db"]["p05"] for v in pvt.values()]
    meds = [s["median"]] + [v["sndr_crest_db"]["median"] for v in pvt.values()]
    return {"median": round(min(meds), 2), "p05": round(min(p05s), 2),
            "p05_all": [round(x, 2) for x in p05s]}


def main():
    rows = []
    print(f"FLICK={FLICK}  OFFS={OFFS}  NMC={NMC}   (median/p05 = worst over MC temps 233/300/398 K)")
    print(f"{'corner':8s} {'slope':>6s} {'D':>6s} | {'c1 rev=1':>16s} | {'c2 rev=0':>16s} | {'c3 rev=0+LUT16':>16s}")
    print("-" * 86)
    for c in CORNERS:
        csv = f"{CSVWIN}/ramp_inl_{c}.csv"
        D = META[c]["D_vs_TT27"]
        slope = META[c]["slope_mV_ns"]
        r1 = run(csv, ["--set", "ramp_inl_reverse=1"], f"{c}_f{FLICK}_c1")
        r2 = run(csv, ["--set", "ramp_inl_reverse=0"], f"{c}_f{FLICK}_c2")
        r3 = run(csv, ["--set", "ramp_inl_reverse=0", "--set", "ramp_lut_points=16",
                       "--set", f"ramp_shape_drift={D}"], f"{c}_f{FLICK}_c3")
        print(f"{c:8s} {slope:6.3f} {D:6.3f} | {r1['median']:6.2f}/{r1['p05']:<8.2f} | "
              f"{r2['median']:6.2f}/{r2['p05']:<8.2f} | {r3['median']:6.2f}/{r3['p05']:<8.2f}")
        rows.append({"corner": c, "slope_mV_ns": slope, "D_vs_TT27": D,
                     "c1_reverse1": r1, "c2_reverse0": r2, "c3_lut16": r3})
    summ = {"flicker_V": FLICK, "offset_V": OFFS, "n_mc": NMC,
            "design_point": "ramp_dnl_sigma=0 v_comp_noise=50e-6 "
                            f"v_comp_flicker={FLICK} v_comp_offset={OFFS} calib=3pt C_int=2pF",
            "rows": rows}
    p = f"{OUT}/summary_f{FLICK}_o{OFFS}.json"
    json.dump(summ, open(p, "w"), indent=2)
    worst = min(min(r["c2_reverse0"]["p05"], r["c3_lut16"]["p05"]) for r in rows)
    print("-" * 86)
    print(f"worst p05 over all corners (c2 & c3): {worst:.2f} dB    -> {p}")


if __name__ == "__main__":
    main()
