#!/usr/bin/env python3
"""Publication figures from paper_stats.json (headless Agg). PNG + PDF (vector).

fig_fp_rates       : mean false-positive lesion rate per region x method — shows how the
                     CC-consensus removes DistMap's spurious lesions.
fig_forest         : matched-pairs rank-biserial effect size for the individual auxiliary
                     losses (DistMap/Kervadec vs baseline and vs each other).
fig_operating_point: region-averaged (specificity, sensitivity) per method — the recall/precision
                     operating points; shows the CC-consensus recovering specificity while
                     keeping DistMap's recall.
"""
import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.abspath(os.path.join(HERE, ".."))
#: Layout de l'ARCHIVE (défaut) — l'archive porte `data/cv_paper_stats.json`. En repli, le
#: layout du projet source BRATS (`outputs/cv_kervadec_paper2/paper_stats.json`) pour que le
#: même fichier tourne aussi là où l'évaluation a été produite.
STATS_CANDIDATS = [
    os.path.join(ARCHIVE, "data", "cv_paper_stats.json"),
    os.path.join(ARCHIVE, "outputs", "cv_kervadec_paper2", "paper_stats.json"),
]
STATS = next((p for p in STATS_CANDIDATS if os.path.exists(p)), STATS_CANDIDATS[0])
OUTDIR = os.path.join(ARCHIVE, "figures")
REGIONS = ["WT", "TC", "ET"]
NAME = {"distmap": "DistMap", "baseline": "Baseline", "kervadec": "Kervadec",
        "consensus_DB": "CC-consensus (Dist∩Base)", "consensus_DK": "CC-consensus (Dist∩Kerv)"}
COL = {"baseline": "#888888", "distmap": "#1f77b4", "kervadec": "#d62728",
       "consensus_DB": "#2ca02c", "consensus_DK": "#9467bd"}
ALL_METHODS = ["baseline", "distmap", "kervadec", "consensus_DB", "consensus_DK"]


def save(fig, stem):
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(OUTDIR, f"{stem}.{ext}"), dpi=200, bbox_inches="tight")
    print("->", stem + ".{png,pdf}")
    plt.close(fig)


def method_mean(stats, field, reg, method):
    """Mean of `field` for `method` in `reg`, read from any pair where it appears."""
    for key, c in stats["metrics"][field]["regions"][reg].items():
        A, B = key.split("_vs_")
        if A == method:
            return c["mean_A"]
        if B == method:
            return c["mean_B"]
    return None


def present_methods(stats):
    return [m for m in ALL_METHODS
            if method_mean(stats, "num_fp", "WT", m) is not None]


def fig_fp_rates(stats):
    methods = present_methods(stats)
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    x = range(len(REGIONS))
    w = 0.8 / len(methods)
    for i, meth in enumerate(methods):
        vals = [method_mean(stats, "num_fp", r, meth) for r in REGIONS]
        off = (i - (len(methods) - 1) / 2) * w
        ax.bar([xi + off for xi in x], vals, w, label=NAME[meth], color=COL[meth])
    ax.set_xticks(list(x))
    ax.set_xticklabels(REGIONS)
    ax.set_ylabel("Mean false-positive lesions / case")
    ax.set_xlabel("Tumor region")
    ax.set_title("Spurious-lesion rate by region (official BraTS-2023 lesion analysis)")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "fig_fp_rates")


def fig_forest(stats):
    metrics = [("lw_dice", "Lesion-wise Dice"), ("lw_hd95", "Lesion-wise HD95"),
               ("legacy_dice", "Legacy Dice"), ("legacy_hd95", "Legacy HD95"),
               ("sensitivity", "Region sensitivity"), ("specificity", "Region specificity")]
    pairs = [("distmap", "baseline"), ("kervadec", "baseline"), ("kervadec", "distmap")]
    fig, ax = plt.subplots(figsize=(7.6, 7.2))
    ylabels, yticks, y = [], [], 0
    for field, lab in metrics:
        for A, B in pairs:
            key = f"{A}_vs_{B}"
            blk = stats["metrics"][field]["regions"]["avg"]
            if key not in blk:
                continue
            c = blk[key]
            sig = c["p_two_sided"] < 0.05
            ax.plot([0, c["rank_biserial"]], [y, y], color=COL[A], lw=1.0, alpha=0.5)
            ax.scatter([c["rank_biserial"]], [y], s=70 if sig else 35, color=COL[A],
                       edgecolor="black" if sig else "none", zorder=3)
            ylabels.append(f"{lab:18s} {NAME[A][:4]}-{NAME[B][:4]}")
            yticks.append(y)
            y += 1
        y += 0.6
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=8, family="monospace")
    ax.set_xlabel("Matched-pairs rank-biserial effect size  (+ favours first method)")
    ax.set_title("Effect sizes on official metrics (region-averaged)\nfilled black edge = p<0.05")
    ax.set_xlim(-0.34, 0.34)
    ax.invert_yaxis()
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "fig_forest")


def fig_operating_point(stats):
    """Recall (voxel sensitivity, up=better) vs precision (mean FP lesions, left=better)."""
    methods = present_methods(stats)
    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    for meth in methods:
        fp = method_mean(stats, "num_fp", "avg", meth)   # lower = better
        se = method_mean(stats, "sensitivity", "avg", meth)
        ax.scatter([fp], [se], s=130, color=COL[meth], zorder=3,
                   edgecolor="black", linewidth=0.6)
        ax.annotate(NAME[meth], (fp, se), fontsize=7.5, xytext=(5, 4),
                    textcoords="offset points")
    ax.invert_xaxis()  # fewer FP (better) to the right
    ax.set_xlabel("← more   |   Mean false-positive lesions / case   |   fewer →  (better)")
    ax.set_ylabel("Region sensitivity (recall)  →  better")
    ax.set_title("Recall–precision operating points (region-averaged)\n"
                 "CC-consensus keeps DistMap's recall while removing its false-positive lesions")
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "fig_operating_point")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stats", default=None,
                    help="statistiques d'entrée (défaut : data/cv_paper_stats.json de l'archive)")
    ap.add_argument("--out", default=None,
                    help="répertoire de sortie (défaut : figures/ de l'archive)")
    ap.add_argument("--with-operating-point", action="store_true",
                    help="rend aussi fig_operating_point, NON cité par le manuscrit et donc "
                         "absent de l'archive par défaut")
    args = ap.parse_args()

    global STATS, OUTDIR
    if args.stats:
        STATS = args.stats
    if args.out:
        OUTDIR = args.out
    if not os.path.exists(STATS):
        sys.exit(f"[err] statistiques introuvables : {STATS}\n"
                 f"       candidats essayés : {STATS_CANDIDATS}")
    os.makedirs(OUTDIR, exist_ok=True)

    with open(STATS) as fh:
        stats = json.load(fh)
    print(f"[in ] {STATS}\n[out] {OUTDIR}")
    fig_fp_rates(stats)
    fig_forest(stats)
    if args.with_operating_point:
        fig_operating_point(stats)
    else:
        print("[skip] fig_operating_point — non cité par le manuscrit "
              "(--with-operating-point pour le rendre)")


if __name__ == "__main__":
    main()
