#!/usr/bin/env python3
"""Collect the per-corner MC JSONs in mc_v2/ into a table + p05 verdict.
Usage: summarize_mc.py <flick-tag>       e.g.  summarize_mc.py 50e-6
"""
import json, os, sys, glob

MC   = r"D:/R/S/H/gcb-papers/data/readout/spice/mc_v2"
META = json.load(open(r"D:/R/S/H/gcb-papers/data/readout/ramp_inl/ramp_inl_meta.json"))
CORNERS = ["tt_-40", "tt_27", "tt_125", "ss_-40", "ss_27", "ss_125", "ff_-40", "ff_27", "ff_125"]
flick = sys.argv[1] if len(sys.argv) > 1 else "50e-6"


def worst(jf):
    j = json.load(open(jf))
    s = j["results"]["sndr_crest_db"]
    pvt = j.get("pvt") or {}
    p05 = [s["p05"]] + [v["sndr_crest_db"]["p05"] for v in pvt.values()]
    med = [s["median"]] + [v["sndr_crest_db"]["median"] for v in pvt.values()]
    return round(min(med), 2), round(min(p05), 2)


rows = []
print(f"flicker={flick}  (median/p05 = worst over MC temps 233/300/398 K, n_mc=200)")
print(f"{'corner':8s} {'slope':>6s} {'D':>6s} | {'c1 rev=1':>13s} | {'c2 rev=0':>13s} | {'c3 LUT16':>13s}")
print("-" * 74)
for c in CORNERS:
    r = {"corner": c, "slope_mV_ns": META[c]["slope_mV_ns"], "D_vs_TT27": META[c]["D_vs_TT27"],
         "INL_rms_pctFS": META[c]["INL_rms_pctFS"]}
    cells = []
    for k in ("c1", "c2", "c3"):
        jf = f"{MC}/{c}_f{flick}_{k}.json"
        if os.path.exists(jf):
            m, p = worst(jf)
            r[k] = {"median": m, "p05": p}
            cells.append(f"{m:5.1f}/{p:<6.1f}")
        else:
            r[k] = None
            cells.append(f"{'--':>12s}")
    print(f"{c:8s} {r['slope_mV_ns']:6.3f} {r['D_vs_TT27']:6.3f} | {cells[0]:>13s} | {cells[1]:>13s} | {cells[2]:>13s}")
    rows.append(r)

done = [r for r in rows if r["c2"] and r["c3"]]
if len(done) == 9:
    wc2 = min(r["c2"]["p05"] for r in rows)
    wc3 = min(r["c3"]["p05"] for r in rows)
    wc1 = min(r["c1"]["p05"] for r in rows if r["c1"])
    print("-" * 74)
    print(f"worst p05:  c1(rev=1) {wc1:.2f}   c2(rev=0) {wc2:.2f}   c3(LUT16) {wc3:.2f}   [target 56.0]")
    verdict = "GO" if min(wc2, wc3) >= 56.0 else "NO-GO"
    print(f"VERDICT (min of c2,c3 worst-corner p05): {verdict}")
json.dump({"flicker": flick, "rows": rows}, open(f"{MC}/SUMMARY_f{flick}.json", "w"), indent=2)
print(f"\nwrote {MC}/SUMMARY_f{flick}.json")
