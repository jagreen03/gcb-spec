#!/usr/bin/env python3
"""
ss_readout_mc.py -- Charge-domain Monte Carlo for the GCB single-slope readout.

Signal path modeled:
    PD photocurrent (2 GHz beat, 512 beats, 256 ns)  ->  passive C_int
    ->  dynamic comparator vs shared ramp  ->  latched count of shared clock
    ->  2-point calibration (reset + dummy reference channel)

Every parameter is labeled in DEFAULTS as one of: spec / derived / assumed.
Noise sources are individually switchable so the breakdown table is exact.

Usage:
    python ss_readout_mc.py                       # defaults, prints report
    python ss_readout_mc.py --n-mc 500 --json out.json
    python ss_readout_mc.py --set C_int=1e-12 --set v_comp_noise=150e-6
    python ss_readout_mc.py --sweep C_int 0.5e-12 1e-12 2e-12 4e-12

Requires numpy only.
"""
import argparse
import json
import math
import sys

import numpy as np

Q_E = 1.602176634e-19
K_B = 1.380649e-23

# ---------------------------------------------------------------------------
# Parameters.  Tag: spec = from directive, derived = computed from spec,
# assumed = engineering assumption that the SPICE step must replace.
# ---------------------------------------------------------------------------
DEFAULTS = {
    # --- optical / directive (spec) ---
    "I_pd_rms": 0.74e-6,        # A     spec
    "crest": 6.0,               # -     spec  (I_FS = crest * I_rms)
    "T_obs": 256e-9,            # s     spec
    "n_beats": 512,             # -     spec
    "K_total": 8192,            # MAC   spec
    "sndr_target_db": 56.0,     # dB    spec
    "inl_target": 0.00224,      # -     spec (0.224 %)
    "energy_target_fj_mac": 20, # fJ    spec
    # --- integrator ---
    "C_int": 2e-12,             # F     assumed (design choice)
    "C_int_tol": 0.10,          # -     assumed  global +/- (PVT, per MC draw)
    "C_vcoef": 100e-6,          # 1/V   assumed  MOM voltage coefficient
    "I_dark": 1e-9,             # A     assumed  PD dark + leakage
    "T_K": 300.0,               # K     nominal; swept by --pvt
    # --- comparator ---
    "v_comp_noise": 100e-6,     # V rms assumed  thermal, input-referred
    "v_comp_flicker": 50e-6,    # V rms assumed  slow 1/f wander conv-to-conv
    "v_comp_offset": 5e-3,      # V     assumed  static offset sigma (cal removes)
    "t_comp_delay": 200e-12,    # s     assumed  constant (cal removes)
    # --- ramp / counter ---
    "f_clk": 6e9,               # Hz    spec (ICO carrier reused as counter clk)
    "clk_phases": 4,            # -     design choice: multi-phase fine TDC (CIS style)
    "n_bits": 12,               # -     design choice (10 b quantization alone < 56 dB)
    "v_ramp_range_over_fs": 1.25,# -    ramp spans 125 % of nominal V_FS (PVT headroom)
    "v_ramp_start": -0.02,      # V     ramp starts below zero (covers offsets)
    "ramp_range_tol": 0.05,     # -     assumed  ramp slope PVT error per draw
    "ramp_dnl_sigma": 0.01,     # LSB   assumed  per-step DNL random walk (0 = analog ramp)
    "ramp_inl_bow": 0.001,      # frac  assumed  midscale bow of shared ramp
    "t_clk_jitter": 2e-12,      # s rms assumed  latch clock jitter
    # --- input statistics / calibration ---
    "x_dist": "halfnormal",     # halfnormal: |N(0,1/crest)| (matches crest def) | uniform
    "x_ref": 0.5,               # dummy-channel reference charge, fraction of FS
    "calib": "2pt",             # 2pt (reset+ref) | 3pt (reset, ref/2, ref: quadratic)
    "cds": 0,                   # 1 = double conversion (reset + signal)
    "n_cal_avg": 16,            # conversions averaged per cal point
    # --- energy (assumed, per output) ---
    "E_comp_pJ": 1.5,           # dynamic comparator, one ramp
    "E_latch_pJ": 0.15,         # n_bits Gray latch
    "E_ramp_share_pJ": 0.5,     # shared ramp gen / 64 channels
    "E_counter_share_pJ": 0.5,  # shared 6 GHz counter / 64 channels
    # --- MC control ---
    "n_mc": 200,
    "n_conv": 2048,
    "seed": 1,
}

SOURCES = ["shot", "ktc", "comp_thermal", "comp_flicker", "clk_jitter",
           "ramp_dnl", "ramp_inl", "cap_vcoef", "dark", "quant"]


# ---------------------------------------------------------------------------
def derived(p):
    d = {}
    d["I_fs"] = p["crest"] * p["I_pd_rms"]
    d["Q_fs"] = d["I_fs"] * p["T_obs"]
    d["Q_rms"] = p["I_pd_rms"] * p["T_obs"]
    d["N_e_fs"] = d["Q_fs"] / Q_E
    d["N_e_rms"] = d["Q_rms"] / Q_E
    d["V_fs"] = d["Q_fs"] / p["C_int"]
    d["V_rms"] = d["Q_rms"] / p["C_int"]
    d["v_ktc"] = math.sqrt(K_B * p["T_K"] / p["C_int"])
    d["v_shot_rms_sig"] = math.sqrt(d["N_e_rms"]) * Q_E / p["C_int"]
    d["shot_limit_db"] = 20 * math.log10(math.sqrt(d["N_e_rms"]))
    d["V_ramp_range"] = d["V_fs"] * p["v_ramp_range_over_fs"]
    d["T_ramp"] = (2 ** p["n_bits"]) / (p["f_clk"] * p["clk_phases"])
    d["ramp_slope"] = d["V_ramp_range"] / d["T_ramp"]
    d["v_lsb"] = d["V_ramp_range"] / 2 ** p["n_bits"]
    return d


def v_on_cap(Q, C, a):
    """Solve Q = C*V*(1 + a*V) for V (MOM voltage coefficient)."""
    if a == 0:
        return Q / C
    return (-1.0 + np.sqrt(1.0 + 4.0 * a * Q / C)) / (2.0 * a)


# ---------------------------------------------------------------------------
class Channel:
    """One PVT/mismatch draw of one channel + its ramp/counter."""

    def __init__(self, p, d, rng, en):
        self.p, self.d, self.rng, self.en = p, d, rng, en
        # global per-draw variations
        self.C = p["C_int"] * (1 + rng.normal(0, p["C_int_tol"] / 3))
        self.a = p["C_vcoef"] if en["cap_vcoef"] else 0.0
        self.offset = rng.normal(0, p["v_comp_offset"])
        self.v_noise = p["v_comp_noise"] * math.sqrt(p["T_K"] / 300.0)
        self.v_ktc = math.sqrt(K_B * p["T_K"] / self.C)
        # ramp thresholds for code k = 0 .. 2^n-1
        n = 2 ** p["n_bits"]
        rng_v = d["V_ramp_range"] * (1 + rng.normal(0, p["ramp_range_tol"] / 3))
        k = np.arange(n, dtype=float)
        if en["ramp_dnl"] and p["ramp_dnl_sigma"] > 0:
            eps = np.cumsum(rng.normal(0, p["ramp_dnl_sigma"], n))
            eps -= np.linspace(eps[0], eps[-1], n)  # remove gain component
        else:
            eps = np.zeros(n)
        u = (k + eps) / n
        if en["ramp_inl"]:
            u = u + 4.0 * p["ramp_inl_bow"] * u * (1 - u)
        self.thr = p["v_ramp_start"] + rng_v * u
        self.v_delay = p["t_comp_delay"] * (rng_v / d["T_ramp"])  # constant
        self.v_jit = p["t_clk_jitter"] * (rng_v / d["T_ramp"])
        self.flick = 0.0

    def integrate(self, x):
        """x in [0,1] of full scale -> charge on C_int (C) with shot noise."""
        p, rng = self.p, self.rng
        N_mean = x * self.d["N_e_fs"]
        if self.en["shot"]:
            # per-beat Poisson (sum is Poisson, kept per-beat for future
            # time-dependent effects such as leakage during the window)
            lam = N_mean / p["n_beats"]
            N = rng.poisson(lam, size=(p["n_beats"],) + np.shape(x)).sum(0)
        else:
            N = N_mean
        Q = N * Q_E
        if self.en["dark"]:
            Q = Q + p["I_dark"] * p["T_obs"]
        return Q

    def one_ramp(self, v):
        """Comparator + ramp + latch: voltage -> integer code."""
        p, rng = self.p, self.rng
        n = np.size(v)
        v = v + self.offset - self.v_delay
        if self.en["comp_thermal"]:
            v = v + rng.normal(0, self.v_noise, n)
        if self.en["comp_flicker"]:
            # slow wander: AR(1) with long correlation, sigma = v_comp_flicker
            steps = rng.normal(0, p["v_comp_flicker"] * 0.3, n)
            f = np.empty(n)
            x = self.flick
            for i in range(n):
                x = 0.95 * x + steps[i]
                f[i] = x
            self.flick = x
            v = v + f
        if self.en["clk_jitter"]:
            v = v + rng.normal(0, self.v_jit, n)
        code = np.searchsorted(self.thr, v, side="right") - 1
        code = np.clip(code, 0, len(self.thr) - 1).astype(float)
        if not self.en["quant"]:
            # ideal continuous readout of the same ramp (for breakdown only)
            code = np.interp(v, self.thr, np.arange(len(self.thr)))
        return code

    def convert(self, x):
        """Full conversion: x -> code (with optional CDS)."""
        Q = self.integrate(x)
        v_sig = v_on_cap(Q, self.C, self.a)
        n = np.size(v_sig)
        ktc = self.rng.normal(0, self.v_ktc, n) if self.en["ktc"] else 0.0
        if self.p["cds"]:
            c_rst = self.one_ramp(np.zeros(n) + ktc)
            c_sig = self.one_ramp(v_sig + ktc)
            return c_sig - c_rst
        return self.one_ramp(v_sig + ktc)

    def calibrate(self):
        """Returns function code -> x_hat from reset + dummy reference channel."""
        m, xr = self.p["n_cal_avg"], self.p["x_ref"]
        if self.p["calib"] == "3pt":
            xs = np.array([0.0, xr / 2, xr])
        else:
            xs = np.array([0.0, xr])
        cs = np.array([self.convert(np.full(m, xi)).mean() for xi in xs])
        coef = np.polyfit(cs, xs, len(xs) - 1)   # exact through the cal points
        return lambda code: np.polyval(coef, code)


# ---------------------------------------------------------------------------
def run_draw(p, d, rng, en, calib="2pt"):
    ch = Channel(p, d, rng, en)
    if p["x_dist"] == "uniform":
        x = rng.uniform(0, 1, p["n_conv"])
    else:
        x = np.minimum(np.abs(rng.normal(0, 1.0 / p["crest"], p["n_conv"])), 1.0)
    code = ch.convert(x)
    if calib != "ideal":
        x_hat = ch.calibrate()(code)
    else:  # ideal least-squares fit: noise+distortion floor only
        A = np.vstack([code, np.ones_like(code)]).T
        g, b = np.linalg.lstsq(A, x, rcond=None)[0]
        x_hat = g * code + b
    r = x_hat - x
    # noise (RMS residual) and INL (bin-averaged residual, noise averaged out)
    rms = float(np.sqrt(np.mean(r ** 2)))
    nb = 32
    x_top = 1.0 if p["x_dist"] == "uniform" else min(1.0, 4.0 / p["crest"])
    idx = np.minimum((x / x_top * nb).astype(int), nb - 1)
    inl_bins = np.array([r[idx == i].mean() for i in range(nb) if np.any(idx == i)])
    inl_rms = float(np.sqrt(np.mean(inl_bins ** 2)))
    inl_max = float(np.max(np.abs(inl_bins)))
    sig_rms = 1.0 / p["crest"]              # directive definition
    sig_sine = 0.5 / math.sqrt(2)           # ADC-convention full-scale sine
    return {
        "rms_resid_fs": rms,
        "sndr_crest_db": 20 * math.log10(sig_rms / rms),
        "sndr_sine_db": 20 * math.log10(sig_sine / rms),
        "inl_rms": inl_rms,
        "inl_max": inl_max,
        "v_resid_uV": rms * d["V_fs"] * 1e6,
    }


def mc(p, d, en, calib=None, seed_off=0):
    calib = calib or p["calib"]
    rng = np.random.default_rng(p["seed"] + seed_off)
    rows = [run_draw(p, d, rng, en, calib) for _ in range(p["n_mc"])]
    out = {}
    for k in rows[0]:
        v = np.array([r[k] for r in rows])
        out[k] = {"median": float(np.median(v)), "p05": float(np.percentile(v, 5)),
                  "p95": float(np.percentile(v, 95)), "min": float(v.min()),
                  "max": float(v.max())}
    return out


def breakdown(p, d):
    """Each noise source alone, ideal calibration, so numbers add in RSS."""
    rows = {}
    for s in SOURCES:
        en = {k: (k == s) for k in SOURCES}
        p2 = dict(p); p2["n_mc"] = max(8, p["n_mc"] // 8)
        res = mc(p2, d, en, calib="ideal")
        rows[s] = res["v_resid_uV"]["median"]
    en = {k: True for k in SOURCES}
    p2 = dict(p); p2["n_mc"] = max(8, p["n_mc"] // 8)
    rows["ALL (ideal cal)"] = mc(p2, d, en, calib="ideal")["v_resid_uV"]["median"]
    return rows


def energy(p):
    E_out = p["E_comp_pJ"] * (2 if p["cds"] else 1) + p["E_latch_pJ"] \
        + p["E_ramp_share_pJ"] + p["E_counter_share_pJ"]
    return E_out, E_out * 1e3 / p["K_total"]  # pJ/output, fJ/MAC


# ---------------------------------------------------------------------------
def report(p, d, res, bd, pvt=None):
    E_out, E_mac = energy(p)
    L = []
    L.append("=== GCB single-slope readout Monte Carlo ===")
    L.append(f"C_int={p['C_int']*1e12:.2f} pF  n_bits={p['n_bits']}  f_clk={p['f_clk']/1e9:.1f} GHz x{p['clk_phases']} ph  "
             f"cds={p['cds']}  calib={p['calib']}  x_dist={p['x_dist']}  T={p['T_K']:.0f} K  n_mc={p['n_mc']}")
    if d["T_ramp"] > p["T_obs"]:
        L.append(f"WARNING: T_ramp {d['T_ramp']*1e9:.0f} ns > T_obs {p['T_obs']*1e9:.0f} ns: "
                 "needs >2 ping-pong integrators or more clock phases")
    L.append(f"Q_FS={d['Q_fs']*1e12:.3f} pC ({d['N_e_fs']:.3g} e-)  V_FS={d['V_fs']*1e3:.1f} mV  "
             f"V_RMS={d['V_rms']*1e3:.1f} mV  LSB={d['v_lsb']*1e6:.0f} uV  T_ramp={d['T_ramp']*1e9:.0f} ns")
    L.append(f"kT/C={d['v_ktc']*1e6:.1f} uV   shot(on RMS sig)={d['v_shot_rms_sig']*1e6:.1f} uV   "
             f"optical shot-noise ceiling={d['shot_limit_db']:.1f} dB")
    L.append("")
    L.append("Noise breakdown (each source alone, ideal cal, uV-equivalent at C_int, median):")
    for k, v in bd.items():
        L.append(f"  {k:18s} {v:8.1f} uV")
    L.append("")
    L.append(f"Full model, {p['calib']} calibration (reset + dummy ref channel at x={p['x_ref']}), all sources on:")
    for k in ["sndr_crest_db", "sndr_sine_db", "inl_rms", "inl_max", "v_resid_uV"]:
        r = res[k]
        L.append(f"  {k:15s} median={r['median']:9.4g}  p05={r['p05']:9.4g}  p95={r['p95']:9.4g}  "
                 f"min={r['min']:9.4g}")
    if pvt:
        L.append("")
        L.append("PVT corners (SNDR crest-def, dB): ")
        for k, v in pvt.items():
            L.append(f"  {k:28s} median={v['sndr_crest_db']['median']:6.2f}  "
                     f"p05={v['sndr_crest_db']['p05']:6.2f}  min={v['sndr_crest_db']['min']:6.2f}  "
                     f"INL_rms p95={v['inl_rms']['p95']*100:.3f} %")
    L.append("")
    L.append(f"Energy (assumed cell numbers): {E_out:.2f} pJ/output -> {E_mac:.3f} fJ/MAC "
             f"(target < {p['energy_target_fj_mac']} fJ/MAC)")
    L.append("")
    ok_sndr = res["sndr_crest_db"]["p05"] >= p["sndr_target_db"]
    ok_inl = res["inl_rms"]["p95"] <= p["inl_target"]
    ok_e = E_mac < p["energy_target_fj_mac"]
    L.append(f"SNDR >= {p['sndr_target_db']} dB at p05 : {'PASS' if ok_sndr else 'FAIL'}")
    L.append(f"INL_rms <= {p['inl_target']*100:.3f} % at p95 : {'PASS' if ok_inl else 'FAIL'}")
    L.append(f"Energy < {p['energy_target_fj_mac']} fJ/MAC          : {'PASS' if ok_e else 'FAIL'}")
    return "\n".join(L)


def parse_set(items):
    out = {}
    for it in items or []:
        k, v = it.split("=", 1)
        out[k] = type(DEFAULTS[k])(float(v)) if isinstance(DEFAULTS[k], (int, float)) and not isinstance(DEFAULTS[k], bool) else v
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", help="override PARAM=value (repeatable)")
    ap.add_argument("--n-mc", type=int)
    ap.add_argument("--cds", type=int, choices=[0, 1])
    ap.add_argument("--calib", choices=["2pt", "3pt"])
    ap.add_argument("--pvt", action="store_true", help="also run T=233/300/398 K corners")
    ap.add_argument("--sweep", nargs="+", help="PARAM v1 v2 ... : SNDR/INL vs parameter")
    ap.add_argument("--json", help="write full results to this file")
    args = ap.parse_args()

    p = dict(DEFAULTS)
    p.update(parse_set(args.set))
    if args.n_mc:
        p["n_mc"] = args.n_mc
    if args.cds is not None:
        p["cds"] = args.cds
    if args.calib:
        p["calib"] = args.calib

    if args.sweep:
        name, vals = args.sweep[0], [float(v) for v in args.sweep[1:]]
        print(f"sweep {name}: value | SNDR_crest median/p05 dB | INL_rms p95 % | resid uV")
        for v in vals:
            p2 = dict(p); p2[name] = v
            d2 = derived(p2)
            en = {k: True for k in SOURCES}
            r = mc(p2, d2, en)
            print(f"  {v:10.4g} | {r['sndr_crest_db']['median']:6.2f} / {r['sndr_crest_db']['p05']:6.2f} | "
                  f"{r['inl_rms']['p95']*100:.3f} | {r['v_resid_uV']['median']:.1f}")
        return

    d = derived(p)
    en = {k: True for k in SOURCES}
    bd = breakdown(p, d)
    res = mc(p, d, en)
    pvt = None
    if args.pvt:
        pvt = {}
        for T in (233.0, 300.0, 398.0):
            p2 = dict(p); p2["T_K"] = T
            pvt[f"T={T:.0f}K"] = mc(p2, derived(p2), en, seed_off=int(T))
    txt = report(p, d, res, bd, pvt)
    print(txt)
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"params": p, "derived": d, "breakdown_uV": bd,
                       "results": res, "pvt": pvt, "energy_pJ_out_fJ_mac": energy(p)}, f, indent=2)
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
