"""Figures for the LLM agent bench (bench/RESULTS_2026-10-09.md §4).

Usage: .venv/bin/python bench/plot_agent.py [--out bench/figures/agent_2026-10-13]
Reads the 14B / 32B per-part table from the results file and the Qwen3.8
scores from bench/runs/agentq38b/scores.json (+ repeat refine runs agentq38r2/r3). A run with no valid model scores 0.
"""
import argparse
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "RESULTS_2026-10-09.md")
Q38 = os.path.join(HERE, "runs/agentq38b/scores.json")
Q38_KEY = "RedHatAI__Qwen3.8-27B-INT4/"
# Repeat refine runs with the same settings (temperature 1.0, so runs differ).
REPEATS = [os.path.join(HERE, f"runs/{t}/scores.json") for t in ("agentq38r2", "agentq38r3")]

PIPE, M14, M32, Q38C, GOOD, BAD = "#5b6878", "#b8c2cf", "#8a96a6", "#1d5bd6", "#1f8a52", "#c4352b"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e6eaef", "axes.axisbelow": True})


def load():
    """{part: {'pipe', '14r', '32r', '14s', '32s', 'q38r', 'q38s'}} for the 10 parts."""
    text = open(RESULTS).read()
    head = "| Part | Pipeline | 14B refine | 32B refine | 14B scratch | 32B scratch |"
    rows = {}
    for line in text[text.index(head):].splitlines()[2:]:
        cells = [c.strip(" *†") for c in line.strip("|").split("|")]
        if not re.fullmatch(r"\d{8}", cells[0]):
            break
        rows[cells[0]] = dict(zip(("pipe", "14r", "32r", "14s", "32s"), map(float, cells[1:6])))
    q = json.load(open(Q38))
    for mode, key in (("refine", "q38r"), ("scratch", "q38s")):
        got = {k[:8]: v["iou"] for k, v in q[Q38_KEY + mode].items() if v.get("valid", True)}
        for p in rows:
            rows[p][key] = got.get(p, 0.0)
    for p in rows:
        rows[p]["reps"] = [rows[p]["q38r"]]
    for path in REPEATS:
        got = {k[:8]: v["iou"] for k, v in json.load(open(path))[Q38_KEY + "refine"].items()
               if v.get("valid", True)}
        for p in rows:
            rows[p]["reps"].append(got.get(p, 0.0))
    return rows


def mean(rows, k):
    return sum(r[k] for r in rows.values()) / len(rows)


def fig_means(rows, out):
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    models = [("Qwen2.5-Coder-14B", "14", M14), ("Qwen2.5-32B", "32", M32), ("Qwen3.8-27B", "q38", Q38C)]
    w = 0.26
    for j, (mode, suf) in enumerate((("refine", "r"), ("scratch", "s"))):
        for i, (lab, k, col) in enumerate(models):
            v = mean(rows, k + suf)
            x = j + (i - 1) * w
            ax.bar(x, v, w * 0.92, color=col, label=lab if j == 0 else None)
            ax.text(x, v + 0.012, f"{v:.3f}", ha="center", fontsize=9,
                    fontweight="bold" if k == "q38" else None)
    p = mean(rows, "pipe")
    ax.axhline(p, color=PIPE, ls="--", lw=1.2)
    ax.text(1.5, p + 0.012, f"pipeline {p:.3f}", ha="right", color=PIPE, fontsize=9)
    ax.set_xticks([0, 1], ["refine\n(starts from the pipeline's model)", "scratch\n(starts empty)"])
    ax.set_ylim(0, 0.85)
    ax.set_ylabel("mean IoU, 10 hardest CADBench parts")
    ax.set_title("LLM agent with CADFit tools: Qwen3.8-27B is the first to beat the pipeline", fontsize=10.5)
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "1_agent_means.png"), dpi=200)
    plt.close(fig)


def fig_parts(rows, out):
    parts = sorted(rows, key=lambda p: rows[p]["q38r"] - rows[p]["pipe"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), sharey=True)
    for ax, (mode, suf) in zip(axes, (("refine", "r"), ("scratch", "s"))):
        for i, p in enumerate(parts):
            a, b, o = rows[p]["pipe"], rows[p]["q38" + suf], rows[p]["32" + suf]
            d = b - a
            col = GOOD if d > 1e-4 else BAD if d < -1e-4 else M32
            ax.plot([a, b], [i, i], color=col, lw=2, zorder=1)
            ax.scatter(a, i, color=PIPE, s=36, zorder=2, label="pipeline" if i == 0 else None)
            ax.scatter(o, i, marker="|", color=M32, s=120, lw=2, zorder=2,
                       label="Qwen2.5-32B" if i == 0 else None)
            ax.scatter(b, i, color=Q38C, s=46, zorder=3, label="Qwen3.8-27B" if i == 0 else None)
            ax.text(1.03, i, f"{d:+.3f}" if abs(d) >= 5e-4 else " 0", va="center", color=col, fontsize=8.5, family="monospace")
        ax.set_xlim(-0.02, 1.0)
        ax.set_yticks(range(len(parts)), parts)
        ax.set_xlabel("IoU")
        n_w = sum(rows[p]["q38" + suf] - rows[p]["pipe"] > 1e-4 for p in parts)
        n_l = sum(rows[p]["q38" + suf] - rows[p]["pipe"] < -1e-4 for p in parts)
        ax.set_title(f"{mode}: mean {mean(rows, 'q38' + suf):.3f} vs pipeline {mean(rows, 'pipe'):.3f}"
                     f"  ({n_w} better / {n_l} worse)", fontsize=10)
    axes[0].legend(frameon=False, loc="lower left", fontsize=8.5)
    fig.suptitle("Qwen3.8-27B agent per part (change vs pipeline at right; 0 = no valid model)", fontsize=10.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "2_agent_per_part.png"), dpi=200)
    plt.close(fig)


def fig_repeats(rows, out):
    gain = lambda p: sum(rows[p]["reps"]) / len(rows[p]["reps"]) - rows[p]["pipe"]
    parts = sorted(rows, key=gain)
    n = len(rows[parts[0]]["reps"])
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    for i, p in enumerate(parts):
        a, reps = rows[p]["pipe"], rows[p]["reps"]
        ax.plot([a, max(reps)], [i, i], color=GOOD if max(reps) - a > 1e-4 else M32, lw=1.5, zorder=1)
        ax.scatter(a, i, color=PIPE, s=36, zorder=2, label="pipeline" if i == 0 else None)
        for j, v in enumerate(reps):  # small vertical offsets so equal scores stay visible
            ax.scatter(v, i + (j - (n - 1) / 2) * 0.18, color=Q38C, s=30, alpha=0.85, zorder=3,
                       edgecolors="white", linewidths=0.5, label="Qwen3.8 refine run" if i == j == 0 else None)
        hits = sum(v - a > 1e-4 for v in reps)
        ax.text(1.03, i, f"{hits}/{n} better", va="center", fontsize=8.5, family="monospace",
                color=GOOD if hits else M32)
    means = [sum(rows[p]["reps"][j] for p in rows) / len(rows) for j in range(n)]
    ax.set_xlim(0, 1.0)
    ax.set_yticks(range(len(parts)), parts)
    ax.set_xlabel("IoU")
    ax.set_title(f"Qwen3.8-27B refine, {n} runs: mean " + " / ".join(f"{m:.3f}" for m in means)
                 + f" vs pipeline {mean(rows, 'pipe'):.3f}\nnever below the pipeline", fontsize=10)
    ax.legend(frameon=False, loc="lower left", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "3_refine_repeats.png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "figures/agent_2026-10-13"))
    out = ap.parse_args().out
    os.makedirs(out, exist_ok=True)
    rows = load()
    fig_means(rows, out)
    fig_parts(rows, out)
    fig_repeats(rows, out)
    print("wrote", sorted(os.listdir(out)))
