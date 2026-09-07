#!/usr/bin/env python3
"""
Comparator input-referred noise / offset / energy roll-up for the GCB
single-slope readout, from ASAP7 (BSIM-CMG OSDI) operating points.

METHOD NOTE.  ngspice-44's OSDI path reports zero small-signal noise in the
`.noise` analysis, and its `trnoise` white-PSD scaling was not reproducible
across timestep settings on this build (a 30x spread on a kT/C reference).
So gates (a) thermal and (b) residual 1/f are computed ANALYTICALLY from the
SPICE-MEASURED operating point (g_m, g_ds, gain, I_dd) plus the cited
ASSUMED PUBLISHED-FinFET PROXIES.  Gate (c) V_os uses the measured gain +
the A_VT proxy.  Gate (d) energy is SPICE-MEASURED (transient supply
integral over a gated 20 ns decision window).

Topology assumed: TWO chopped + auto-zeroed gain stages (each = the measured
NMOS-pair / resistor-load stage) + StrongARM latch.  A single stage only
reaches gain 5-9 on 0.8 V, too low to bury the latch noise; two stages give
G_tot = G1*G2 ~ 30-80.

Proxies (assumed published FinFET):
  gamma  = 1.0                thermal excess-noise factor (short-channel)
  K_Fn   = 5e-11 V^2 * um^2   input-referred flicker, S_vg = K_Fn/(W L f)
  A_VT   = 2.0 mV * um        Pelgrom Vth mismatch
"""
import math, json

KB, T = 1.380649e-23, 300.0
kT = KB * T

# SPICE-MEASURED, ASAP7 TT/27, per gain stage: NMOS pair nfin=8 L=24n, NMOS
# tail mirror, resistor loads ~0.40 V drop.
MEAS = {   # I_tail(A): (R_L, gm_in, gds_in, gain1=gm*RL, E20_fJ/MAC_1stage+latch)
    15e-6: (53333, 167e-6, 2.75e-6, 8.9, 0.4278),
    22e-6: (36364, 218e-6, 3.62e-6, 7.9, 0.4394),
    30e-6: (26667, 266e-6, 4.48e-6, 7.1, 0.4517),
    40e-6: (20000, 317e-6, 5.43e-6, 6.3, 0.4664),
    50e-6: (16000, 359e-6, 6.26e-6, 5.7, 0.4801),
    60e-6: (13333, 395e-6, 6.99e-6, 5.3, 0.4934),
}
NFIN_IN, L_IN = 8, 24e-9
WFIN = 2 * 32e-9 + 6.5e-9
WL_IN_um2 = (NFIN_IN * WFIN) * L_IN * 1e12          # 0.01354 um^2

GAMMA, K_FN, A_VT = 1.0, 5e-11, 2.0e-3
F_CHOP = 20e6
T_CONV = 256e-9
T_GATE = 20e-9
V_LATCH_IN = 0.8e-3          # StrongARM input-referred noise before /G_tot (assumed)
Q_INJ_V    = 0.6e-3          # AZ charge-injection residual (assumed, dummy switches + 300 fF)


def thermal_stage_vn(gm, RL, C_L):
    Sv = 8 * kT * GAMMA / gm + 8 * kT / (gm * gm * RL)     # V^2/Hz, pair + 2 loads
    NBW = 1.0 / (4 * RL * C_L)
    return math.sqrt(Sv * NBW), NBW


def flicker_resid_vn():
    f_conv = 1.0 / (T_CONV + 50e-9)
    f_lo = f_conv / 20.0
    Svg0 = K_FN / WL_IN_um2
    v2_az = Svg0 * 0.5 * (1 - (f_lo / f_conv) ** 2)        # auto-zero only
    supp = (f_conv / F_CHOP) ** 2                          # chopper fold-back
    return math.sqrt(v2_az * supp * 3.0), math.sqrt(v2_az)  # 3x model margin


def run(C_L):
    v1f, v1f_az = flicker_resid_vn()
    rows = []
    for It in sorted(MEAS):
        RL, gm, gds, g1, e1 = MEAS[It]
        Gtot = g1 * g1                                     # two identical stages
        vth1, NBW = thermal_stage_vn(gm, RL, C_L)          # stage-1 thermal (dominant)
        vth2 = vth1 / g1                                   # stage-2, referred to input
        vlat = V_LATCH_IN / Gtot
        v_th_tot = math.sqrt(vth1 ** 2 + vth2 ** 2 + vlat ** 2)
        v_total = math.sqrt(v_th_tot ** 2 + v1f ** 2)
        sig_dev = A_VT / math.sqrt(WL_IN_um2)
        sig_pair = math.sqrt(2) * sig_dev
        vos_res_1s = sig_pair / (1 + Gtot) + Q_INJ_V
        e_tot = e1 + It * 0.8 * T_GATE / 8192 * 1e15       # + 2nd stage static
        rows.append(dict(
            I_tail_uA=It * 1e6, gain1=g1, Gtot=round(Gtot, 1),
            NBW_MHz=round(NBW / 1e6, 1),
            v_thermal_stage1_uV=round(vth1 * 1e6, 1),
            v_latch_ref_uV=round(vlat * 1e6, 1),
            v_thermal_total_uV=round(v_th_tot * 1e6, 1),
            v_1f_resid_uV=round(v1f * 1e6, 1),
            v_total_uV=round(v_total * 1e6, 1),
            Vos_raw_3sig_mV=round(sig_pair * 3e3, 1),
            Vos_resid_3sig_mV=round(vos_res_1s * 3e3, 2),
            E_fJ_per_MAC=round(e_tot, 3),
        ))
    return rows, v1f, v1f_az


if __name__ == "__main__":
    for C_L in (0.6e-12, 0.8e-12, 1.0e-12):
        rows, v1f, v1f_az = run(C_L)
        print(f"=== C_L = {C_L*1e12:.1f} pF ;  F_chop = {F_CHOP/1e6:.0f} MHz ;  "
              f"1/f resid = {v1f*1e6:.1f} uV (AZ-only {v1f_az*1e6:.0f} uV) ;  "
              f"T_gate = {T_GATE*1e9:.0f} ns ===")
        print(("{:>5} {:>6} {:>6} {:>7} {:>9} {:>8} {:>9} {:>6} {:>8} {:>11} {:>11} {:>9}")
              .format("I_uA", "G1", "Gtot", "NBW_MHz", "vth_s1_uV", "vlat_uV",
                      "vth_tot", "v1f", "V_TOTAL", "Vos3s_raw", "Vos3s_res", "E_fJ/MAC"))
        for r in rows:
            flag = "  <= 55" if r["v_total_uV"] <= 55 else ""
            print(("{I_tail_uA:5.0f} {gain1:6.1f} {Gtot:6.1f} {NBW_MHz:7.1f} "
                   "{v_thermal_stage1_uV:9.1f} {v_latch_ref_uV:8.1f} "
                   "{v_thermal_total_uV:9.1f} {v_1f_resid_uV:6.1f} {v_total_uV:8.1f} "
                   "{Vos_raw_3sig_mV:11.1f} {Vos_resid_3sig_mV:11.2f} "
                   "{E_fJ_per_MAC:9.3f}").format(**r) + flag)
        print()
        if abs(C_L - 0.8e-12) < 1e-15:
            json.dump({"proxies": {"gamma": GAMMA, "K_Fn_V2um2": K_FN, "A_VT_Vum": A_VT},
                       "knobs": {"C_L_pF": C_L * 1e12, "F_chop_MHz": F_CHOP / 1e6,
                                 "T_gate_ns": T_GATE * 1e9, "topology": "2-stage chopped AZ preamp + StrongARM"},
                       "rows": rows},
                      open("/mnt/d/R/S/H/gcb-papers/data/readout/spice/comparator_noise.json", "w"),
                      indent=2)
