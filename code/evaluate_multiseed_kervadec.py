"""
Multi-seed variance evaluation — Kervadec vs Baseline (Paper 2).

3 seeds x (baseline, kervadec) on fold 0 (240 patients).
Computes official BraTS-2023 lesion-wise + legacy metrics,
CC-consensus filter (K∩B per seed), statistical tables.

Usage (on tour):
  cd ~/Bureau/BRATS
  taskset -c 0-13 python3 scripts/evaluate_multiseed_kervadec.py

Outputs (outputs/multiseed_kervadec/):
  per_patient.csv              per (config, seed, patient, region)
  consensus_KB/seed{N}/        CC-consensus NIfTI predictions (persistent)
  consensus_per_patient.csv    same format for K∩B
  stats.json                   mean±std, Wilcoxon, t-test per metric/region
  table_variance.md            paper-ready markdown
"""
import csv, gc, json, os, sys, time, traceback
import multiprocessing as mp
from pathlib import Path

import cc3d
import nibabel as nib
import numpy as np
from scipy.stats import ttest_rel, wilcoxon

os.sched_setaffinity(0, range(0, 14))

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
METRICS   = ROOT / "external" / "BraTS-2023-Metrics"
sys.path.insert(0, str(METRICS))
from metrics import get_LesionWiseResults  # noqa: E402

RESULTS   = ROOT / "nnunet_data"
GT_DIR    = ROOT / "nnunet_data" / "raw" / "Dataset001_BraTS2023GLI" / "labelsTr"
PLAN      = "nnUNetPlans_96GB_mednext"
DS        = "Dataset001_BraTS2023GLI"
OUT       = ROOT / "outputs" / "multiseed_kervadec"
CHALLENGE = "BraTS-GLI"

SEEDS   = [1, 2, 3]
CONFIGS = ["baseline", "kervadec"]
TRAINERS = {
    "baseline": "nnUNetTrainerMedNeXtBaseline",
    "kervadec": "nnUNetTrainerMedNeXtKervadec",
}
REGIONS  = ["WT", "TC", "ET"]
FIELDS   = ["config", "seed", "patient_id", "region",
            "legacy_dice", "lw_dice", "legacy_hd95", "lw_hd95",
            "num_tp", "num_fp", "num_fn", "sensitivity", "specificity"]


def val_dir(cfg, seed):
    tr = TRAINERS[cfg]
    return (RESULTS / f"results_seed{seed}" / DS /
            f"{tr}__{PLAN}__3d_fullres" / "fold_0" / "validation")

def cons_dir(seed):
    d = OUT / "consensus_KB" / f"seed{seed}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── CC-consensus K∩B ──────────────────────────────────────────────────────────
def apply_cc_consensus(kv_arr, bl_arr):
    """Keep Kervadec CCs that overlap any baseline label."""
    out = np.zeros_like(kv_arr)
    for lv in [1, 2, 3]:
        mask = (kv_arr == lv)
        if not mask.any():
            continue
        bl_any = (bl_arr > 0)
        labeled, n = cc3d.connected_components(mask, return_N=True)
        for cid in range(1, n + 1):
            comp = labeled == cid
            if (comp & bl_any).any():
                out[comp] = lv
    return out


def make_consensus_predictions(seed):
    """Write CC-consensus K∩B NIfTIs for one seed; skip existing."""
    kv_d = val_dir("kervadec", seed)
    bl_d = val_dir("baseline", seed)
    cd   = cons_dir(seed)
    written = 0
    for pf in sorted(kv_d.glob("*.nii.gz")):
        dst = cd / pf.name
        if dst.exists():
            continue
        bf = bl_d / pf.name
        if not bf.exists():
            continue
        kv_img = nib.load(str(pf))
        bl_arr = nib.load(str(bf)).get_fdata().astype(np.int16)
        kv_arr = kv_img.get_fdata().astype(np.int16)
        cons   = apply_cc_consensus(kv_arr, bl_arr)
        nib.save(nib.Nifti1Image(cons.astype(np.int16), kv_img.affine,
                                 kv_img.header), str(dst))
        written += 1
        del kv_arr, bl_arr, cons
        gc.collect()
    return written


# ── Per-patient evaluation ─────────────────────────────────────────────────────
def eval_one(args):
    pred_path, gt_path, cfg, seed, pid = args
    try:
        df = get_LesionWiseResults(pred_path, gt_path, CHALLENGE)
        df = df.set_index("Labels")
        rows = []
        for reg in REGIONS:
            r = df.loc[reg]
            rows.append({
                "config":      cfg,
                "seed":        seed,
                "patient_id":  pid,
                "region":      reg,
                "legacy_dice": float(r["Legacy_Dice"]),
                "lw_dice":     float(r["LesionWise_Score_Dice"]),
                "legacy_hd95": float(r["Legacy_HD95"]),
                "lw_hd95":     float(r["LesionWise_Score_HD95"]),
                "num_tp":      float(r["Num_TP"]),
                "num_fp":      float(r["Num_FP"]),
                "num_fn":      float(r["Num_FN"]),
                "sensitivity": float(r["Sensitivity"]),
                "specificity": float(r["Specificity"]),
            })
        return rows
    except Exception:
        sys.stderr.write(f"FAIL {cfg} seed{seed} {pid}\n{traceback.format_exc()}\n")
        return None


def build_tasks_for(cfg, seed, pred_root=None):
    if pred_root is None:
        pred_root = val_dir(cfg, seed)
    tasks = []
    for pf in sorted(pred_root.glob("*.nii.gz")):
        pid = pf.name.replace(".nii.gz", "")
        gt  = GT_DIR / f"{pid}.nii.gz"
        if gt.exists():
            tasks.append((str(pf), str(gt), cfg, seed, pid))
    return tasks


def _worker_fn(task, result_q):
    try:
        result_q.put(eval_one(task))
    except Exception:
        result_q.put(None)


def run_eval(tasks, out_csv, workers=12, timeout=90):
    """Evaluate tasks with per-task timeout, stream-write CSV durable."""
    all_rows = []
    out_csv  = Path(out_csv)
    mode     = "a" if out_csv.exists() else "w"
    with open(out_csv, mode, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if mode == "w":
            writer.writeheader()

        n = len(tasks)
        for batch_start in range(0, n, workers):
            batch = tasks[batch_start:batch_start + workers]
            result_q = mp.Queue()
            procs = []
            for task in batch:
                p = mp.Process(target=_worker_fn, args=(task, result_q), daemon=True)
                p.start()
                procs.append(p)

            deadline = time.time() + timeout
            for p in procs:
                remaining = max(0.1, deadline - time.time())
                p.join(timeout=remaining)
                if p.is_alive():
                    print(f"TIMEOUT killing PID {p.pid}", flush=True)
                    p.kill()
                    p.join()

            collected = 0
            while not result_q.empty():
                try:
                    result = result_q.get_nowait()
                    if result:
                        for row in result:
                            writer.writerow(row)
                            all_rows.append(row)
                        collected += 1
                except Exception:
                    break

            done_so_far = batch_start + len(batch)
            print(f"    {done_so_far}/{n}  (batch wrote {collected})", flush=True)
            if done_so_far % 200 == 0 or done_so_far == n:
                fh.flush()
                os.fsync(fh.fileno())

        fh.flush()
        os.fsync(fh.fileno())
    return all_rows


# ── Statistics ─────────────────────────────────────────────────────────────────
def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows

def get_val(row, metric):
    v = row.get(metric, "")
    return float(v) if v not in ("", "nan", "inf") else np.nan

def seed_means(rows, cfg, metric, region):
    out = []
    for s in SEEDS:
        vals = [get_val(r, metric) for r in rows
                if r["config"] == cfg and int(r["seed"]) == s
                and r["region"] == region and not np.isnan(get_val(r, metric))]
        out.append(np.mean(vals) if vals else np.nan)
    return out

def patient_vals(rows, cfg, metric, region):
    return [get_val(r, metric) for r in rows
            if r["config"] == cfg and r["region"] == region
            and not np.isnan(get_val(r, metric))]

def compute_stats(main_rows, cons_rows):
    stats = {}
    for metric in ["legacy_dice", "lw_dice", "legacy_hd95", "lw_hd95"]:
        for region in REGIONS:
            key = f"{metric}_{region}"
            mb = seed_means(main_rows, "baseline",  metric, region)
            mk = seed_means(main_rows, "kervadec",  metric, region)
            mb, mk = np.array(mb), np.array(mk)
            t, pt = ttest_rel(mk, mb)
            pvb = patient_vals(main_rows, "baseline", metric, region)
            pvk = patient_vals(main_rows, "kervadec", metric, region)
            n   = min(len(pvb), len(pvk))
            _, pwc = wilcoxon(pvk[:n], pvb[:n]) if n >= 10 else (np.nan, np.nan)
            stats[key] = {
                "mean_baseline":  float(mb.mean()), "std_baseline":  float(mb.std()),
                "mean_kervadec":  float(mk.mean()), "std_kervadec":  float(mk.std()),
                "per_seed_baseline": mb.tolist(), "per_seed_kervadec": mk.tolist(),
                "delta_mean": float((mk - mb).mean()),
                "p_ttest": float(pt), "p_wilcoxon": float(pwc), "n_wilcoxon": n,
            }
            # CC-consensus K∩B vs baseline
            mc  = seed_means(cons_rows, "consensus_KB", metric, region)
            mc  = np.array(mc)
            tc, ptc = ttest_rel(mc, mb)
            pvc = patient_vals(cons_rows, "consensus_KB", metric, region)
            n2  = min(len(pvb), len(pvc))
            _, pwcc = wilcoxon(pvc[:n2], pvb[:n2]) if n2 >= 10 else (np.nan, np.nan)
            stats[f"cons_{key}"] = {
                "mean_baseline":  float(mb.mean()), "std_baseline":  float(mb.std()),
                "mean_consensus": float(mc.mean()), "std_consensus": float(mc.std()),
                "per_seed_consensus": mc.tolist(),
                "delta_mean": float((mc - mb).mean()),
                "p_ttest": float(ptc), "p_wilcoxon": float(pwcc), "n_wilcoxon": n2,
            }
    return stats


# ── Tables ─────────────────────────────────────────────────────────────────────
def pstar(p):
    if np.isnan(p): return ""
    if p < 0.001:   return "†"
    if p < 0.05:    return "*"
    return ""

def fmt(v, d=4):
    return f"{v:.{d}f}" if not (np.isnan(v) or np.isinf(v)) else "—"

def write_markdown(path, stats):
    lines = [
        "## Multi-seed variance — Kervadec vs Baseline (fold 0, seeds 1-3, n=240/seed)\n",
        "Δ = Kervadec − Baseline (mean across 3 seeds). "
        "Seed-level paired t-test (n=3). Wilcoxon pooled n=720 pairs.\n",
        "* raw p<0.05 ; † p<0.001\n",
        "",
        "### Kervadec vs Baseline",
        "",
        "| Metric | Region | Baseline (mean±σ) | Kervadec (mean±σ) | Δ | p t-test | p Wilcoxon |",
        "|---|---|---|---|---|---|---|",
    ]
    for metric, label in [
        ("legacy_dice", "Legacy Dice"),
        ("lw_dice",     "LW Dice"),
        ("legacy_hd95", "Legacy HD95 mm"),
        ("lw_hd95",     "LW HD95 mm"),
    ]:
        for reg in REGIONS:
            s = stats[f"{metric}_{reg}"]
            delta = s["mean_kervadec"] - s["mean_baseline"]
            lines.append(
                f"| {label} | {reg} "
                f"| {fmt(s['mean_baseline'])}±{fmt(s['std_baseline'])} "
                f"| {fmt(s['mean_kervadec'])}±{fmt(s['std_kervadec'])} "
                f"| {delta:+.4f} "
                f"| {fmt(s['p_ttest'])}{pstar(s['p_ttest'])} "
                f"| {fmt(s['p_wilcoxon'])}{pstar(s['p_wilcoxon'])} |"
            )
        lines.append("|  |  |  |  |  |  |  |")

    lines += [
        "", "### CC-consensus (K∩B) vs Baseline", "",
        "| Metric | Region | Baseline (mean±σ) | CC(K∩B) (mean±σ) | Δ | p t-test | p Wilcoxon |",
        "|---|---|---|---|---|---|---|",
    ]
    for metric, label in [
        ("legacy_dice", "Legacy Dice"),
        ("lw_dice",     "LW Dice"),
        ("legacy_hd95", "Legacy HD95 mm"),
        ("lw_hd95",     "LW HD95 mm"),
    ]:
        for reg in REGIONS:
            s = stats[f"cons_{metric}_{reg}"]
            delta = s["mean_consensus"] - s["mean_baseline"]
            lines.append(
                f"| {label} | {reg} "
                f"| {fmt(s['mean_baseline'])}±{fmt(s['std_baseline'])} "
                f"| {fmt(s['mean_consensus'])}±{fmt(s['std_consensus'])} "
                f"| {delta:+.4f} "
                f"| {fmt(s['p_ttest'])}{pstar(s['p_ttest'])} "
                f"| {fmt(s['p_wilcoxon'])}{pstar(s['p_wilcoxon'])} |"
            )
        lines.append("|  |  |  |  |  |  |  |")

    lines += ["", "### Per-seed detail (Legacy Dice avg WT+TC+ET / 3)", ""]
    lines.append("| Config | seed1 | seed2 | seed3 | mean±σ |")
    lines.append("|---|---|---|---|---|")
    for cfg_key, label in [("baseline", "Baseline"), ("kervadec", "Kervadec")]:
        per_seed = []
        for reg in REGIONS:
            s  = stats[f"legacy_dice_{reg}"]
            ps = s[f"per_seed_{cfg_key}"]
            per_seed.append(ps)
        avgs = [np.mean([per_seed[ri][si] for ri in range(3)]) for si in range(3)]
        m, sd = np.mean(avgs), np.std(avgs)
        lines.append(
            f"| {label} | {fmt(avgs[0])} | {fmt(avgs[1])} | {fmt(avgs[2])} | {fmt(m)}±{fmt(sd)} |"
        )

    txt = "\n".join(lines) + "\n"
    with open(path, "w") as f:
        f.write(txt)
        f.flush()
        os.fsync(f.fileno())
    print(f"  -> {path}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    per_csv  = OUT / "per_patient.csv"
    cons_csv = OUT / "consensus_per_patient.csv"

    print("\n[1/4] Evaluating baseline + kervadec (6 × 240 patients)...")
    if per_csv.exists():
        existing = load_csv(per_csv)
        done = {(r["config"], r["seed"], r["patient_id"]) for r in existing}
        print(f"  {len(done)} (config,seed,patient) combos already done")
    else:
        done = set()

    all_tasks = []
    for cfg in CONFIGS:
        for seed in SEEDS:
            tasks = build_tasks_for(cfg, seed)
            skip  = sum(1 for t in tasks if (cfg, str(seed), t[4]) in done)
            run   = [t for t in tasks if (cfg, str(seed), t[4]) not in done]
            print(f"  {cfg} seed{seed}: {len(tasks)} total, {skip} skip, {len(run)} to run")
            all_tasks.extend(run)

    if all_tasks:
        print(f"  Running {len(all_tasks)} tasks...")
        run_eval(all_tasks, per_csv)
    else:
        print("  All done, skipping.")

    print("\n[2/4] Computing CC-consensus K∩B predictions...")
    for seed in SEEDS:
        n = make_consensus_predictions(seed)
        total = len(list(cons_dir(seed).glob("*.nii.gz")))
        print(f"  seed{seed}: wrote {n} new, {total} total NIfTIs")

    print("  Evaluating consensus predictions...")
    if cons_csv.exists():
        existing_c = load_csv(cons_csv)
        done_c = {(r["config"], r["seed"], r["patient_id"]) for r in existing_c}
    else:
        done_c = set()

    cons_tasks = []
    for seed in SEEDS:
        cd    = cons_dir(seed)
        tasks = build_tasks_for("consensus_KB", seed, pred_root=cd)
        run   = [t for t in tasks if ("consensus_KB", str(seed), t[4]) not in done_c]
        print(f"  seed{seed}: {len(run)} to run")
        cons_tasks.extend(run)

    if cons_tasks:
        run_eval(cons_tasks, cons_csv)

    print("\n[3/4] Computing statistics...")
    main_rows = load_csv(per_csv)
    cons_rows = load_csv(cons_csv)
    print(f"  main: {len(main_rows)} rows, consensus: {len(cons_rows)} rows")

    stats = compute_stats(main_rows, cons_rows)

    stats_path = OUT / "stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    print(f"  -> {stats_path}")

    print("\n[4/4] Generating tables...")
    write_markdown(OUT / "table_variance.md", stats)

    print("\n=== SUMMARY (Legacy Dice / LW Dice) ===")
    print(f"{'':22} {'Baseline':>14} {'Kervadec':>14} {'Δ':>8} {'p(t)':>8} {'p(wc)':>9}")
    for metric, tag in [("legacy_dice", "Leg"), ("lw_dice", "LW")]:
        for reg in REGIONS:
            s = stats[f"{metric}_{reg}"]
            d = s["mean_kervadec"] - s["mean_baseline"]
            print(f"  {tag} Dice {reg:2s}        "
                  f"{s['mean_baseline']:.4f}±{s['std_baseline']:.4f}  "
                  f"{s['mean_kervadec']:.4f}±{s['std_kervadec']:.4f}  "
                  f"{d:+.4f}  {s['p_ttest']:.4f}  {s['p_wilcoxon']:.4f}")

    print("\n=== CC-consensus K∩B vs Baseline (LW Dice) ===")
    for reg in REGIONS:
        s = stats[f"cons_lw_dice_{reg}"]
        d = s["mean_consensus"] - s["mean_baseline"]
        print(f"  LW Dice {reg}: baseline={s['mean_baseline']:.4f}  "
              f"cons={s['mean_consensus']:.4f}  Δ={d:+.4f}  p={s['p_ttest']:.4f}")

    print("\n=== ALL DONE ===")

if __name__ == "__main__":
    main()
