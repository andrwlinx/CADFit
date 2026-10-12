"""Figures for the 2026-10-10 fixes (bench/RESULTS_2026-10-09.md §2, §5, §6).

Usage: .venv/bin/python bench/plot_fixes.py [--out bench/figures/fixes_2026-10-10]
Reads the abc60b soup-judge scores, the abc40 per-part table in the results
file and the abc60b meshes (to split open / watertight / multi-body parts).
"""
import argparse
import glob
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "RESULTS_2026-10-09.md")
SCORES = os.path.join(HERE, "runs/abc60b_ws/abc60b_pscores.json")          # before the fixes
# Same parts with the fixes: abc60c, with the 10 parts that failed there taken
# from their re-run with the later fixes (abc60r).
SCORES_FIXED = os.path.join(HERE, "runs/abc60c_ws/abc60cr_pscores.json")
ABC60B = os.path.join(HERE, "drive/abc60b")

# Gap between the winding-number solid's bounds and the input's, in grid
# cells, for the repairs the fix declines (scratch/fixcheck/gwn.log, workstation).
DECLINED = {"00000648": 3.3, "00002081": 8.5, "00002336": 29.5,
            "00002152": 492.5, "00002402": 2.4}
GAP_LIMIT = 1.5

BEAM, GWN, DECL, SINGLE, GOOD, BAD = "#8a96a6", "#1d5bd6", "#c47a00", "#5b6878", "#1f8a52", "#c4352b"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e6eaef", "axes.axisbelow": True})


def mesh_classes():
    out = {}
    for p in sorted(glob.glob(os.path.join(ABC60B, "*.stl"))):
        m = trimesh.load(p, force="mesh")
        part = os.path.basename(p)[:-4]
        out[part] = "soup" if not m.is_watertight else ("multi" if m.body_count > 1 else "single")
    return out


def abc40_rows():
    txt = open(RESULTS).read()
    pat = r"^\| (\d{8}) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|$"
    return [dict(p=m[1], base=float(m[2]), base_r=float(m[3]), beam=float(m[4]), beam_r=float(m[5]))
            for m in re.finditer(pat, txt, re.M)]


def fig_scatter(out, fixed=False):
    tag = "abc60c" if fixed else "abc60b"
    d = json.load(open(SCORES_FIXED if fixed else SCORES))
    b, g = d[f"{tag}_beam"], d[f"{tag}_beamgwn"]
    cls = mesh_classes()
    style = {"soup": (GWN, "open soup"), "multi": (DECL, "watertight, several bodies"),
             "single": (SINGLE, "watertight, one body")}
    fig, ax = plt.subplots(figsize=(6.4, 6.2))
    ax.plot([0, 1], [0, 1], ls="--", c="#999", lw=1)
    for c, (col, lab) in style.items():
        parts = [p for p in b if cls[p] == c]
        ok = [p for p in parts if b[p].get("valid", True) and g[p].get("valid", True)]
        bad = [p for p in parts if p not in ok]
        ax.scatter([b[p]["iou"] for p in ok], [g[p]["iou"] for p in ok], s=34, c=col,
                   edgecolors="white", linewidths=0.6, label=f"{lab} ({len(parts)})")
        ax.scatter([b[p]["iou"] for p in bad], [g[p]["iou"] for p in bad], s=46, c=col, marker="x")
    ax.scatter([], [], marker="x", c="k", label="a run failed (scored 0)")
    if not fixed:
        ax.annotate("00001387: greedy step hung", (b["00001387"]["iou"] - 0.015, 0), xytext=(0.6, 0.03),
                    va="center", arrowprops=dict(arrowstyle="->", color="#555"), fontsize=9)
    ax.annotate("beam failed,\nrepair gave a model", (0, 0.86), xytext=(0.08, 0.93), fontsize=9)
    n = len(b)
    mb = sum(v["iou"] for v in b.values()) / n
    mg = sum(v["iou"] for v in g.values()) / n
    ax.set(xlim=(-0.03, 1.02), ylim=(-0.03, 1.02), xlabel="beam IoU", ylabel="beam + repair IoU",
           title=f"abc60b held-out, 60 parts ({'with the fixes, failed parts re-run' if fixed else 'before the fixes'})\n"
                 f"mean {mb:.3f} → {mg:.3f}")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 0.09), fontsize=8.5, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "1b_abc60c_with_fixes.png" if fixed else "1_abc60b_beam_vs_repair.png"), dpi=200)
    plt.close(fig)


def fig_dumbbell(out):
    rows = sorted(abc40_rows(), key=lambda r: r["beam_r"] - r["beam"])
    fig, ax = plt.subplots(figsize=(8, 8.2))
    for i, r in enumerate(rows):
        dec = r["p"] in DECLINED
        col = DECL if dec else GWN
        ax.plot([r["beam"], r["beam_r"]], [i, i], c=col, alpha=0.45, lw=3)
        ax.scatter(r["beam"], i, c=BEAM, s=40, zorder=3)
        ax.scatter(r["beam_r"], i, s=40, zorder=3, c="white" if dec else GWN,
                   edgecolors=col, linewidths=1.8 if dec else 0)
        dd = r["beam_r"] - r["beam"]
        tc = DECL if dec else GOOD if dd > 0.01 else BAD if dd < -0.01 else "#777"
        ax.text(1.03, i, f"{dd:+.3f}", va="center", color=tc, fontsize=8.5, family="monospace")
    ax.set_yticks(range(len(rows)), [r["p"] for r in rows], fontsize=8.5, family="monospace")
    for t in ax.get_yticklabels():
        if t.get_text() in DECLINED:
            t.set_color(DECL); t.set_fontweight("bold")
    ax.scatter([], [], c=BEAM, label="beam, no repair")
    ax.scatter([], [], c=GWN, label="beam + old repair")
    ax.scatter([], [], c="white", edgecolors=DECL, linewidths=1.8,
               label="old repair, now declined (falls back to beam)")
    ax.set(xlim=(0, 1.0), ylim=(-0.8, len(rows) - 0.2), xlabel="IoU (soup judge)",
           title="abc40, 27 open-soup parts: beam vs beam + repair, sorted by change")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07), ncols=3, fontsize=8.5, frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "2_abc40_soups_repair_change.png"), dpi=200)
    plt.close(fig)


def fig_gaps(out):
    rows = sorted(DECLINED.items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.barh([p for p, _ in rows], [v for _, v in rows], color=DECL, left=0.1)
    for i, (_, v) in enumerate(rows):
        ax.text(v * 1.15, i, f"{v}", va="center", fontsize=9)
    ax.axvline(GAP_LIMIT, c="k", ls="--", lw=1.2)
    ax.text(GAP_LIMIT * 1.08, len(rows) - 0.45, f"limit {GAP_LIMIT} cells", fontsize=8.5)
    ax.set_xscale("log")
    ax.set(xlim=(1, 2000), xlabel="gap between repaired solid and input bounds (grid cells, log)",
           title="Repairs now declined\n(the old code stretched the solid across this gap)")
    ax.grid(axis="y", visible=False)
    for t in ax.get_yticklabels():
        t.set_family("monospace")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "3_declined_bounds_gap.png"), dpi=200)
    plt.close(fig)


def fig_flow(out):
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.set_axis_off(); ax.set(xlim=(0, 10), ylim=(0, 10))
    box = dict(boxstyle="round,pad=0.45", fc="white", ec="#444")
    dia = dict(boxstyle="round4,pad=0.45", fc="#eef3fc", ec=GWN)
    nodes = {"in": (5, 9.2, "Input mesh", box), "wt": (5, 7.5, "Watertight?", dia),
             "grid": (5, 5.6, "Winding-number solid on grid", box),
             "gap": (5, 3.8, f"Bounds gap ≤ {GAP_LIMIT} cells?", dia),
             "use": (2.2, 1.6, "Stretch to input bounds,\nuse the solid", box),
             "dec": (7.8, 1.6, "Decline, write .declined;\nuse the input mesh", dict(box, ec=DECL)),
             "inp": (8.6, 7.5, "Use the input mesh", box)}
    for x, y, t, st in nodes.values():
        ax.text(x, y, t, ha="center", va="center", bbox=st, fontsize=9.5)
    arrows = [((5, 8.85), (5, 7.95), "", None), ((5, 7.05), (5, 6.05), "no", (5.2, 6.55)),
              ((6.0, 7.5), (7.25, 7.5), "yes", (6.45, 7.7)), ((5, 5.15), (5, 4.25), "", None),
              ((4.4, 3.35), (2.6, 2.15), "yes", (3.2, 2.95)), ((5.6, 3.35), (7.4, 2.15), "no", (6.6, 2.95))]
    for (x0, y0), (x1, y1), lab, at in arrows:
        ax.annotate("", (x1, y1), (x0, y0), arrowprops=dict(arrowstyle="->", color="#444"))
        if lab:
            ax.text(*at, lab, fontsize=9, color="#555")
    ax.set_title("--gwn-repair after the fixes", fontsize=11)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "4_repair_decision.png"), dpi=200)
    plt.close(fig)


def fig_estimate(out):
    # Measured means, the §6 estimate (declined and watertight parts take their
    # no-repair score), and, for abc60b, the measured re-run with the fixes.
    d = json.load(open(SCORES_FIXED))
    fixed = sum(v["iou"] for v in d["abc60c_beamgwn"].values()) / len(d["abc60c_beamgwn"])
    groups = [("abc40 soups\nbase + repair", 0.586, 0.656, 0.690, None),
              ("abc40 soups\nbeam + repair", 0.677, 0.689, 0.728, None),
              ("abc60b (60 parts)\nbeam + repair", 0.560, 0.641, 0.657, fixed)]
    fig, ax = plt.subplots(figsize=(7.6, 4))
    w = 0.2
    for i, (n, ref, meas, est, new) in enumerate(groups):
        bars = [(i - 1.5 * w, ref, dict(color=BEAM), "no repair", "{:.3f}"),
                (i - 0.5 * w, meas, dict(color=GWN), "repair, before fixes", "{:.3f}"),
                (i + 0.5 * w, est, dict(color="white", edgecolor=GWN, hatch="///"),
                 "repair, with fixes (estimate)", "~{:.3f}")]
        if new is not None:
            bars.append((i + 1.5 * w, new, dict(color=GOOD), "repair, with fixes (measured)", "{:.3f}"))
        for x, v, st, lab, fmt in bars:
            ax.bar(x, v, w, label=lab if i == len(groups) - 1 else None, **st)
            ax.text(x, v + 0.004, fmt.format(v), ha="center", fontsize=8)
    ax.set_xticks(range(len(groups)), [g[0] for g in groups])
    ax.set(ylim=(0.5, 0.76), ylabel="mean IoU (axis starts at 0.5)",
           title="Mean IoU before and with the fixes")
    ax.grid(axis="x", visible=False)
    ax.legend(fontsize=8.5, loc="upper center", ncols=2, bbox_to_anchor=(0.5, -0.17), frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "5_expected_effect.png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "figures/fixes_2026-10-10"))
    out = ap.parse_args().out
    os.makedirs(out, exist_ok=True)
    for f in (fig_scatter, fig_dumbbell, fig_gaps, fig_flow, fig_estimate):
        f(out)
    fig_scatter(out, fixed=True)
    print("wrote", sorted(os.listdir(out)))
