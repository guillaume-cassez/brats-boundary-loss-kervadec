# Paper 2 — Precision Pays: A Fixed-Weight Boundary Loss Anchors the Precision End of a Recall–Precision Axis and Wins as the Consensus Veto under the Official BraTS-2023 Metrics

**Reproducibility archive** · BRATS auxiliary-loss program · **v2.6** (2026-09-22) · CC-BY-4.0

> Guillaume Cassez (ORCID 0009-0007-0987-3931) · Stanislas Larnier — Independent research.
> **Zenodo** — concept DOI [10.5281/zenodo.22906446](https://doi.org/10.5281/zenodo.22906446) (resolves to the latest version) · version DOI [10.5281/zenodo.22906447](https://doi.org/10.5281/zenodo.22906447) · v2.6, 2026-09-22.

## What this is

This archive accompanies **Paper 2** of the BRATS auxiliary-loss program. It tests whether adding
the Kervadec boundary loss (fixed weight λ = 0.05, acting on the logits, **no** auxiliary head) to
a strong MedNeXt/nnU-Net glioma backbone improves adult glioma segmentation, evaluated under the
**complete official BraTS-2023 metric set** over a 5-fold held-out cross-validation on the
**1196-case study set**.

The headline is a **transparently reported negative result**: the boundary loss is **not
significant** versus the baseline on any pre-specified primary or region-averaged official metric
(lesion-wise Dice Δ = +0.000, Holm p = 0.34; lesion-wise HD95 Δ = −0.58 mm, p = 0.31), and a
3-seed multiseed check confirms the null (paired t-test p = 0.42). Its one robust distinctive
property is being the **precision-oriented mirror** of a signed-distance (SDT) auxiliary head —
more specific, fewer spurious tumor-core/enhancing lesions, lower recall — which makes it an
effective connected-component **consensus veto**: as the veto it removes ~half of the SDT model's
false-positive lesions at negligible recall cost (lesion-wise HD95 −9.95 mm, p = 2.3×10⁻²⁰, 5-fold
CV), and as the primary model with a baseline veto it reproduces the companion paper's consensus
gain (lesion-wise Dice WT +3.89 pp, p = 0.005, 3 seeds × fold 0).

### Where the 1196 cases come from

The unified BraTS-2023 GLI download holds **1251** cases; the nnU-Net dataset that every training
run and every metric of this paper uses holds **1196**. `analysis/DATASET_EXCLUSIONS.md` (French
mirror: `analysis/DATASET_EXCLUSIONS_fr.md`) lists the **55** dropped cases one by one — trigger,
git date of the triggering entry — and re-measures their file integrity against 55 included
controls: **0** unreadable file, **0** NaN/Inf, **0** out-of-set label, **0** divergent affine,
(240, 240, 155) everywhere. It is therefore a **conservative, patient-level precaution** recorded
in March 2026, upstream of every training run and every metric — not the correction of a measured
file defect, and no reported figure changes because of it. Supporting artefacts:
`analysis/exclusions_1251_to_1196.csv` (the 55 identifiers), `analysis/exclusions_1251_to_1196.json`
(measured audit summary), `analysis/integrite_exclus_vs_temoins.{json,csv}`,
`analysis/sonde_5_cas_exacts.json` (the five 2026-03 flags, re-measured on the literal code path of
that audit: none reproduces), `analysis/comparaison_3_copies.tsv` (the three surviving copies of
the dataset give one fingerprint per file) and `analysis/folds.csv` (the partition is disjoint and
its validation folds union to exactly the 1196 cases). These notes are **byte-identical** to those
shipped with the companion Paper 1 record: same measurements, same generator.

## Contents

```
.zenodo.json                                 Deposit metadata (publication / preprint / CC-BY-4.0)
CITATION.cff                                 How to cite this work (CFF 1.2.0)
LICENSE                                      CC-BY-4.0, full legal code
README.md                                    This file
analysis/DATASET_EXCLUSIONS.md               Measured provenance of the 55 exclusions (1251 -> 1196)
analysis/DATASET_EXCLUSIONS_fr.md            Idem, French
analysis/comparaison_3_copies.tsv            Three surviving copies of the dataset, one fingerprint per file
analysis/exclusions_1251_to_1196.csv         The 55 excluded identifiers + trigger + git date
analysis/exclusions_1251_to_1196.json        Measured summary of the 1251 -> 1196 audit
analysis/folds.csv                           5-fold partition: disjoint, validation folds union = the 1196 cases
analysis/integrite_exclus_vs_temoins.csv     Per-file detail of that re-measurement
analysis/integrite_exclus_vs_temoins.json    File-integrity re-measurement: 55 excluded vs 55 controls
analysis/sonde_5_cas_exacts.json             The five 2026-03 flags, re-measured on the literal audit code path
code/eval_lesionwise_kervadec.py             Official BraTS-2023 lesion-wise + legacy metrics
code/evaluate_multiseed_kervadec.py          3 seeds x fold 0 robustness -> data/multiseed_stats.json
code/make_figures.py                         Renders the two cited figures (--with-operating-point for the uncited one)
code/make_tables.py                          Renders tables/ (+ companion tables in outputs/) from data/
code/nnUNetTrainerMedNeXtKervadec.py         Boundary-loss trainer (lambda = 0.05, theta0 = 30, no auxiliary head)
code/paper_stats.py                          Paired Wilcoxon, rank-biserial r, bootstrap CI, Holm/BH -> data/
data/cv_paper_stats.json                     Every cross-validation number in the manuscript
data/multiseed_stats.json                    Every 3-seed x fold-0 official-metric number (section 4.4)
data/nnunet_validation_dice_multiseed.json   The six training-log validation Dice + both t-test readings (section 4.4)
data/patient_level_clean_BKD.json            Patient-level counts behind the Figure 3-5 captions (clean regime)
figures/fig_forest.pdf                       Idem, vector
figures/fig_forest.png                       Rank-biserial effect sizes with CI (manuscript Figure 1)
figures/fig_fp_rates.pdf                     Idem, vector
figures/fig_fp_rates.png                     Spurious-lesion rate by region x method (manuscript Figure 2)
figures/figviewer_P2A_kervadec_sauve.png     Pinned viewer case P2A - Kervadec rescues (Figure 3)
figures/figviewer_P2B_kervadec_echoue.png    Pinned viewer case P2B - Kervadec fails (Figure 4)
figures/figviewer_P2C_distmap_sauve.png      Pinned viewer case P2C - SDT head rescues (Figure 5)
manuscript.md                                Paper, English (source of record)
manuscript.pdf                               Paper, English, rendered PDF (15 pages)
manuscript_fr.md                             Paper, French
manuscript_fr.pdf                            Paper, French, rendered PDF (17 pages)
outputs/cv_kervadec_paper2/table_consensus.md CC-consensus comparisons (D∩K, D∩B)
outputs/cv_kervadec_paper2/table_consensus.tex Idem, LaTeX
outputs/cv_kervadec_paper2/table_paper1.md   Companion comparison (DistMap vs Baseline), rendered by code/make_tables.py
outputs/cv_kervadec_paper2/table_paper1.tex  Idem, LaTeX
references.bib                               Verified reference list (15 cited entries, 20 available)
tables/table_paper2.md                       Kervadec vs Baseline and vs DistMap (Markdown)
tables/table_paper2.tex                      Idem (LaTeX booktabs)
MANIFEST.sha256                              sha256 of every file in this archive
```

### `code/`

| File | Role |
|------|------|
| `nnUNetTrainerMedNeXtKervadec.py` | The boundary-loss trainer: `seg_loss + λ·mean(softmax(logits)·SDT_signed)`, θ₀ = 30, fixed λ = 0.05, no auxiliary head. |
| `eval_lesionwise_kervadec.py` | Runs the official BraTS-2023 lesion-wise + legacy metrics on the predictions. |
| `paper_stats.py` | Paired Wilcoxon, rank-biserial r + bootstrap CI, Holm / Benjamini–Hochberg corrections → `data/cv_paper_stats.json`. |
| `make_tables.py` | Renders `tables/table_paper2.{md,tex}` (plus the companion tables in `outputs/`) from the stats JSON. |
| `make_figures.py` | Renders the two cited figures (`--with-operating-point` also renders a third one the manuscript does not cite, hence not shipped). |
| `evaluate_multiseed_kervadec.py` | 3-seed × fold-0 robustness analysis → `data/multiseed_stats.json`. |

## Reproducing the numbers

Every number in the manuscript can be checked **without a GPU**: the result JSONs ship in `data/`,
and the generators accept exactly the command line written here (both were run inside this archive
on the build host, matplotlib 3.10.7, on 2026-09-22):

```bash
python3 code/make_tables.py  --stats data/cv_paper_stats.json --out tables/
python3 code/make_figures.py --stats data/cv_paper_stats.json --out figures/
python3 -c "import json;print(json.load(open('data/patient_level_clean_BKD.json'))['comptes'])"
```

* `code/make_tables.py` re-renders the shipped tables **byte-for-byte** from
  `data/cv_paper_stats.json`: md5 `2ae77e41c16789cd…` for `table_paper2.md`,
  `4fb40c572b4f0b6f…` for `table_paper2.tex` (measured identical to the regenerated files).
* `code/make_figures.py` re-renders the two cited figures with **identical embedded text**
  (`pdftotext -layout` on the vector PDFs: 80 words for `fig_forest`,
  36 for `fig_fp_rates`, 0 differing lines). Their **bytes** differ from the
  shipped PNG/PDF only because those were rendered with the July-2026 toolchain; the shipped
  figures are kept because they are the ones the co-author reviewed.
* `data/patient_level_clean_BKD.json` carries the patient-level counts quoted by the Figure 3-5
  captions (415/1196 = 34.7 % see the boundary-loss model beat both other arms, 346 = 28.9 % see
  the baseline win, 433 = 36.2 % see the SDT head win) and the nine pinned-case scores, recomputed
  under the official **`clean`** component-cleanup regime — the same regime as every official
  metric in this paper. Under the `raw` regime the same three counts would be 421 / 347 / 427: the
  artefact records both so the regime is never ambiguous.
* `data/nnunet_validation_dice_multiseed.json` carries the six training-log validation Dice values
  behind §4.4 and **both** t-test readings — on values already rounded to 4 decimals (t = 0.96,
  p = 0.44, what was printed before v2.6) and at full precision (t = −1.02, p = 0.42, what this
  revision states). Both are far from significance at df = 2.

Reproducing from raw predictions needs the upstream environment (not vendored here): **nnU-Net v2**
with the **MedNeXt** extension, the official **BraTS-2023 metrics** package, the BraTS-2023
adult-glioma (GLI) dataset and the signed-SDT cache. Training used the official nnU-Net 5-fold
splits, MedNeXt-B (`3d_fullres`, `nnUNetPlans_96GB_mednext`), Dice + cross-entropy with deep
supervision, 300 epochs/fold, on an RTX PRO 6000.

### Paths quoted in the manuscript ↔ source project

Since v2.6 every path quoted in the manuscript resolves **inside this archive**. The source
project (BRATS) keeps the same files under other names:

| In this archive | In the source project |
|---|---|
| `code/paper_stats.py` | `scripts/paper_stats.py` |
| `code/eval_lesionwise_kervadec.py` | `scripts/eval_lesionwise_kervadec.py` |
| `code/evaluate_multiseed_kervadec.py` | `scripts/evaluate_multiseed_kervadec.py` |
| `code/make_tables.py` · `code/make_figures.py` | `scripts/make_tables.py` · `scripts/make_figures.py` |
| `code/nnUNetTrainerMedNeXtKervadec.py` | `src/trainers/nnUNetTrainerMedNeXtKervadec.py` |
| `data/cv_paper_stats.json` | `outputs/cv_kervadec_paper2/paper_stats.json` |
| `data/multiseed_stats.json` | `outputs/multiseed_kervadec/stats.json` |

The provenance note also names the **generators of its own measurements**, which stay in the
source project because they read the 41 GB dataset (`scripts/audit_exclusions_1251_1196.py`,
`scripts/audit_exclusions_integrity.py`, `scripts/sonde_5_cas_exclus.py`,
`scripts/compare_3_copies_exclus.sh`, `scripts/paper1_exclusions_provenance.py`,
`scripts/paper2_export_patient_level.py`, `scripts/paper2_export_nnunet_dice.py`). Their
**outputs** are all shipped here.

## Methodological note

Only **benchmark-epoch** results (300 epochs/fold, comparable to published teams) appear in the
manuscript. Short exploration/screening runs (e.g. the 50-epoch λ screening of §3.3) justify
hyper-parameter choices and are **never** reported as results. Program-wide method (decision of
2026-08-22): 3 seeds and 5 folds.

## Companion records

| | Record | Covers |
|---|---|---|
| Paper 1 | concept DOI [10.5281/zenodo.19695263](https://doi.org/10.5281/zenodo.19695263) — v10, record 22904810 | The SDT auxiliary head: recall end of the axis |
| Paper 3 | concept DOI [10.5281/zenodo.22776410](https://doi.org/10.5281/zenodo.22776410) — v0.13, record 22903668 | Expert-initialised MoE: the gate does not choose |

This paper cites Paper 1 by name 13 times, including the CC(D∩B) consensus figures of its section
4.6 (lesion-wise Dice WT +4.28 pp, lesion-wise HD95 WT −17.2 mm, 3 seeds × fold 0) quoted in §4.4.

## How to cite

Cite this record by its Zenodo concept DOI [10.5281/zenodo.22906446](https://doi.org/10.5281/zenodo.22906446), which resolves to the latest version, or by the version DOI [10.5281/zenodo.22906447](https://doi.org/10.5281/zenodo.22906447) for exactly this revision (v2.6, 2026-09-22). Full metadata in `CITATION.cff`.

## License

All materials in this archive — manuscript, figures, tables, data, provenance artefacts and code —
are released together as a single publication record under the **Creative Commons Attribution 4.0
International (CC-BY-4.0)** license. See `LICENSE`. You are free to share and adapt with
attribution.
