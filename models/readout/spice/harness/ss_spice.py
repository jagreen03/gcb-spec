#!/usr/bin/env python3
"""
ss_spice.py -- ASAP7 (BSIM-CMG via OSDI) transient proof harness for the
GCB single-slope readout comparator + ramp.  ngspice-44 self-built with
--enable-osdi;  BSIM-CMG 111 compiled from VA-Models with OpenVAF 23.5.

Every reported number is tagged  M(easured) / D(erived) / A(ssumed).

Sub-commands:
    ramp     gate (e) ramp INL over 0..0.71 V + slope + current droop
    corner   gate (f) SS / 125 C ramp-top behaviour at 0.72 V
    offset   gate (c) 3-sigma input-referred V_os, 200-run mismatch MC
    thermal  gate (a) input-referred thermal at the crossing (trnoise histogram)
    energy   gate (d) energy per AZ+compare decision
"""
import os, re, sys, json, subprocess, tempfile, statistics, math, argparse

HOME   = os.path.expanduser("~")
TB     = f"{HOME}/gcb_spice/tb"
OUT    = f"{HOME}/gcb_spice/out"
NG     = f"{HOME}/opt/ngspice/bin/ngspice"
OSDI   = f"{TB}/bsimcmg.osdi"
MODEL  = {"tt": "7nm_tt_osdi.pm", "ss": "7nm_ss_osdi.pm", "ff": "7nm_ff_osdi.pm"}

KB = 1.380649e-23
Q  = 1.602176634e-19

os.makedirs(OUT, exist_ok=True)


def run(deck_text, tag, extra_files=None):
    """Write deck to TB (so relative includes/pre_osdi resolve), run ngspice -b."""
    path = f"{TB}/_run_{tag}.cir"
    with open(path, "w") as f:
        f.write(deck_text)
    p = subprocess.run([NG, "-b", os.path.basename(path)], cwd=TB,
                       capture_output=True, text=True, timeout=1800)
    return p.stdout + p.stderr


def read_wrdata(fn):
    """ngspice wrdata: whitespace cols, pairs of (x,y) per vector -> take x once + all y."""
    rows = []
    with open(f"{TB}/{fn}") as f:
        for ln in f:
            v = ln.split()
            if not v:
                continue
            try:
                rows.append([float(x) for x in v])
            except ValueError:
                continue
    return rows


def linfit(xs, ys):
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    d = n * sxx - sx * sx
    a = (n * sxy - sx * sy) / d          # slope
    b = (sy - a * sx) / n                # intercept
    return a, b


# ---------------------------------------------------------------- ramp / corner
def cmd_ramp(args):
    model = MODEL[args.corner_model]
    temp  = args.temp
    vbs   = args.vbs
    deck = open(f"{TB}/ramp.cir").read()
    deck = deck.replace("MODELFILE", model).replace("OUTFILE", f"_ramp_{args.tag}.txt")
    deck = re.sub(r"\.param VBS=[\d.]+", f".param VBS={vbs}", deck)
    deck = re.sub(r"\.param NF=\d+", f".param NF={args.nf}", deck)
    if temp is not None:
        deck = deck.replace(".control\npre_osdi",
                            f".options temp={temp}\n.control\npre_osdi")
    log = run(deck, args.tag)
    m = re.search(r"slope\s*=\s*([-\d.eE+]+)", log)
    slope = float(m.group(1)) if m else float("nan")
    rows = read_wrdata(f"_ramp_{args.tag}.txt")
    # rows: [t, v(rmp), t, iramp]  (wrdata repeats x per vector)
    t  = [r[0] for r in rows]
    vr = [r[1] for r in rows]
    ir = [r[3] for r in rows if len(r) > 3]
    # analysis window 0.05 .. 0.70 V, rising
    win = [(ti, vi) for ti, vi in zip(t, vr) if 0.050 <= vi <= 0.700]
    xs = [w[0] for w in win]
    ys = [w[1] for w in win]
    a, b = linfit(xs, ys)
    resid = [vi - (a * ti + b) for ti, vi in win]
    inl_v = max(abs(r) for r in resid)
    span = 0.71
    inl_pct = 100.0 * inl_v / span
    # current droop bottom->top of the same window
    iwin = [ii for ii, vi in zip(ir, vr) if 0.050 <= vi <= 0.700] if ir else []
    droop_pct = (100.0 * (iwin[0] - iwin[-1]) / iwin[0]) if len(iwin) > 2 else float("nan")
    vtop = max(vr)
    res = {
        "model": model, "temp_C": temp if temp is not None else 27,
        "vbs": vbs, "nfin": args.nf,
        "slope_mV_per_ns__M": slope / 1e6,
        "ramp_INL_pct_of_FS__M": inl_pct,
        "ramp_INL_V__M": inl_v,
        "I_droop_0p05_to_0p70V_pct__M": droop_pct,
        "v_ramp_top_reached_V__M": vtop,
        "n_pts_window": len(win),
    }
    print(json.dumps(res, indent=2))
    with open(f"{OUT}/{args.tag}.json", "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("ramp")
    r.add_parser = None
    r.add_argument("--tag", default="ramp_tt27")
    r.add_argument("--corner-model", dest="corner_model", default="tt", choices=list(MODEL))
    r.add_argument("--temp", type=float, default=None)
    r.add_argument("--vbs", type=float, default=0.512)
    r.add_argument("--nf", type=int, default=1)
    r.set_defaults(func=cmd_ramp)

    args = ap.parse_args()
    args.func(args)
