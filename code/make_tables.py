#!/usr/bin/env python3
"""Generate publication tables (Markdown + LaTeX/booktabs) from paper_stats.json.

Honest reporting: every official metric shown, per region + avg, with effect size and
Holm-corrected p. One main table (4 core official metrics) + one detection table
(FP/FN/sensitivity/specificity) per paper. Paper 1 = DistMap vs baseline; Paper 2 =
Kervadec vs baseline and vs DistMap.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.abspath(os.path.join(HERE, ".."))
#: Layout de l'ARCHIVE d'abord (`data/cv_paper_stats.json`, `tables/`), layout du projet source
#: en repli (`outputs/cv_kervadec_paper2/`) : le même fichier tourne dans les deux contextes.
STATS_CANDIDATS = [
    os.path.join(ARCHIVE, "data", "cv_paper_stats.json"),
    os.path.join(ARCHIVE, "outputs", "cv_kervadec_paper2", "paper_stats.json"),
]
STATS = next((p for p in STATS_CANDIDATS if os.path.exists(p)), STATS_CANDIDATS[0])
TABLESDIR = os.path.join(ARCHIVE, "tables")
OUTDIR = os.path.join(ARCHIVE, "outputs", "cv_kervadec_paper2")
REGIONS = ["WT", "TC", "ET", "avg"]
CORE = [("lw_dice", "Lesion-wise Dice", 3), ("lw_hd95", "Lesion-wise HD95 (mm)", 2),
        ("legacy_dice", "Legacy Dice", 3), ("legacy_hd95", "Legacy HD95 (mm)", 2)]
DETECT = [("num_fp", "FP lesions", 3), ("num_fn", "FN lesions", 3),
          ("sensitivity", "Sensitivity", 3), ("specificity", "Specificity", 3)]
NAME = {"distmap": "DistMap", "baseline": "Baseline", "kervadec": "Kervadec",
        "consensus_DB": "CC(D∩B)", "consensus_DK": "CC(D∩K)"}


def cell(stats, field, reg, A, B, dec):
    c = stats["metrics"][field]["regions"][reg][f"{A}_vs_{B}"]
    p, ph = c["p_two_sided"], c.get("p_holm_3region", float("nan"))
    star = "*" if p < 0.05 else ""
    star_h = "†" if (ph == ph and ph < 0.05) else ""
    return {"a": f"{c['mean_A']:.{dec}f}", "b": f"{c['mean_B']:.{dec}f}",
            "d": f"{c['mean_delta']:+.{dec}f}", "r": f"{c['rank_biserial']:+.2f}",
            "wl": f"{c['n_win_A']}/{c['n_loss_A']}",
            "p": f"{p:.3f}{star}" if p >= 1e-3 else f"{p:.1e}{star}",
            "ph": ("--" if ph != ph else (f"{ph:.3f}{star_h}" if ph >= 1e-3 else f"{ph:.1e}{star_h}"))}


def md_table(stats, A, B, metrics, title):
    L = [f"### {title} ({NAME[A]} vs {NAME[B]})", "",
         f"Δ = {NAME[A]} − {NAME[B]}. r = matched-pairs rank-biserial (+ favours {NAME[A]}). "
         f"\\* raw p<0.05; † Holm-corrected p<0.05 (across the 3 regions). n="
         f"{stats['n_patients']}.", "",
         "| Metric | Region | " + NAME[A] + " | " + NAME[B] + " | Δ | r | win/loss | p | p(Holm) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for field, lab, dec in metrics:
        for reg in REGIONS:
            x = cell(stats, field, reg, A, B, dec)
            mlab = lab if reg == "WT" else ""
            L.append(f"| {mlab} | {reg} | {x['a']} | {x['b']} | {x['d']} | {x['r']} | "
                     f"{x['wl']} | {x['p']} | {x['ph']} |")
    return "\n".join(L) + "\n"


def tex_table(stats, A, B, metrics, title, label):
    rows = []
    for field, lab, dec in metrics:
        for i, reg in enumerate(REGIONS):
            x = cell(stats, field, reg, A, B, dec)
            mlab = f"\\multirow{{4}}{{*}}{{{lab}}}" if i == 0 else ""
            p = x["p"].replace("*", "$^{*}$")
            ph = x["ph"].replace("†", "$^{\\dagger}$")
            rows.append(f"{mlab} & {reg} & {x['a']} & {x['b']} & {x['d']} & {x['r']} & "
                        f"{x['wl']} & {p} & {ph} \\\\")
        rows.append("\\midrule")
    body = "\n".join(rows)
    return (f"\\begin{{table}}[t]\n\\centering\n\\caption{{{title} ({NAME[A]} vs {NAME[B]}, "
            f"5-fold held-out CV, $n={stats['n_patients']}$). $\\Delta={NAME[A]}-{NAME[B]}$; "
            f"$r$ matched-pairs rank-biserial ($+$ favours {NAME[A]}); $^{{*}}$ raw $p<0.05$; "
            f"$^{{\\dagger}}$ Holm-corrected $p<0.05$.}}\n\\label{{{label}}}\n"
            f"\\begin{{tabular}}{{llcccccrr}}\n\\toprule\n"
            f"Metric & Region & {NAME[A]} & {NAME[B]} & $\\Delta$ & $r$ & win/loss & $p$ & "
            f"$p_{{\\mathrm{{Holm}}}}$ \\\\\n\\midrule\n{body}\n\\bottomrule\n"
            f"\\end{{tabular}}\n\\end{{table}}\n")


def primary_block(stats, A, B):
    pe = stats["primary_endpoints"][f"{A}_vs_{B}"]
    L = [f"**Pre-specified primary endpoints** ({NAME[A]} vs {NAME[B]}, region-averaged "
         "official ranking metrics, Holm-corrected across the 2-metric family):", ""]
    for f, lab in [("lw_dice", "Lesion-wise Dice"), ("lw_hd95", "Lesion-wise HD95")]:
        d = pe[f]
        verdict = "**significant**" if d["holm_p"] < 0.05 else "not significant"
        L.append(f"- {lab}: Δ={d['delta']:+.3f}, r={d['rank_biserial']:+.3f}, "
                 f"raw p={d['raw_p']:.3g}, Holm p={d['holm_p']:.3g} → {verdict}")
    return "\n".join(L) + "\n"


def write(path, text):
    with open(path, "w") as fh:
        fh.write(text)
    print("->", os.path.relpath(path, OUTDIR))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stats", default=None,
                    help="statistiques d'entrée (défaut : data/cv_paper_stats.json de l'archive)")
    ap.add_argument("--out", default=None,
                    help="répertoire des tables `table_paper2.*` (défaut : tables/ de l'archive)")
    ap.add_argument("--out-companion", default=None,
                    help="répertoire des tables compagnes `table_paper1.*` / `table_consensus.*` "
                         "(défaut : outputs/cv_kervadec_paper2/ de l'archive)")
    args = ap.parse_args()

    global STATS, TABLESDIR, OUTDIR
    if args.stats:
        STATS = args.stats
    if args.out:
        TABLESDIR = args.out
    if args.out_companion:
        OUTDIR = args.out_companion
    if not os.path.exists(STATS):
        sys.exit(f"[err] statistiques introuvables : {STATS}\n"
                 f"       candidats essayés : {STATS_CANDIDATS}")
    os.makedirs(OUTDIR, exist_ok=True)
    os.makedirs(TABLESDIR, exist_ok=True)
    with open(STATS) as fh:
        stats = json.load(fh)
    print(f"[in ] {STATS}\n[out] {TABLESDIR} · compagnes {OUTDIR}")
    # Paper 1
    p1 = (primary_block(stats, "distmap", "baseline") + "\n"
          + md_table(stats, "distmap", "baseline", CORE, "Paper 1 — Official ranking & legacy metrics")
          + "\n" + md_table(stats, "distmap", "baseline", DETECT, "Paper 1 — Lesion detection"))
    write(os.path.join(OUTDIR, "table_paper1.md"), p1)
    write(os.path.join(OUTDIR, "table_paper1.tex"),
          tex_table(stats, "distmap", "baseline", CORE, "Paper 1 official metrics", "tab:p1_main")
          + "\n" + tex_table(stats, "distmap", "baseline", DETECT, "Paper 1 lesion detection", "tab:p1_det"))
    # Paper 2 (Kervadec) — 4 tables: {main, detection} x {vs baseline, vs distmap}
    p2 = primary_block(stats, "kervadec", "baseline") + "\n" \
        + primary_block(stats, "kervadec", "distmap") + "\n"
    for A, B in [("kervadec", "baseline"), ("kervadec", "distmap")]:
        p2 += md_table(stats, A, B, CORE, "Paper 2 — Official ranking & legacy metrics") + "\n"
        p2 += md_table(stats, A, B, DETECT, "Paper 2 — Lesion detection") + "\n"
    write(os.path.join(TABLESDIR, "table_paper2.md"), p2)
    t2 = ""
    for A, B in [("kervadec", "baseline"), ("kervadec", "distmap")]:
        t2 += tex_table(stats, A, B, CORE, f"Paper 2 official metrics ({NAME[A]} vs {NAME[B]})",
                        f"tab:p2_{B}_main") + "\n"
        t2 += tex_table(stats, A, B, DETECT, f"Paper 2 lesion detection ({NAME[A]} vs {NAME[B]})",
                        f"tab:p2_{B}_det") + "\n"
    write(os.path.join(TABLESDIR, "table_paper2.tex"), t2)
    # CC-consensus (Paper 1 payoff): does the veto recover precision without losing recall?
    cc = ""
    for A, B in [("consensus_DK", "baseline"), ("consensus_DB", "baseline"),
                 ("consensus_DK", "distmap"), ("consensus_DB", "distmap"),
                 ("consensus_DK", "consensus_DB")]:
        if f"{A}_vs_{B}" not in stats["metrics"]["lw_dice"]["regions"]["avg"]:
            continue
        cc += primary_block(stats, A, B) + "\n"
        cc += md_table(stats, A, B, CORE, "CC-consensus — official ranking & legacy") + "\n"
        cc += md_table(stats, A, B, DETECT, "CC-consensus — detection") + "\n"
    if cc:
        write(os.path.join(OUTDIR, "table_consensus.md"), cc)
        tc = ""
        for A, B in [("consensus_DK", "baseline"), ("consensus_DK", "distmap")]:
            if f"{A}_vs_{B}" in stats["metrics"]["lw_dice"]["regions"]["avg"]:
                tc += tex_table(stats, A, B, CORE, f"CC-consensus ({NAME[A]} vs {NAME[B]})",
                                f"tab:cc_{B}") + "\n"
        write(os.path.join(OUTDIR, "table_consensus.tex"), tc)


if __name__ == "__main__":
    main()
