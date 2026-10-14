# Aster poster sources and interpretation

1. [ASAP–Polaris–OpenADMET dataset](https://doi.org/10.5281/zenodo.15582067) — Experimental potency source for milestone 1.

2. [RDKit](https://www.rdkit.org/docs/GettingStartedInPython.html) — Structure parsing, Morgan fingerprints and scaffold identities; reused throughout.

3. [scikit-learn](https://scikit-learn.org/stable/) — Random forests, ridge regression, preprocessing, CV and evaluation metrics.

4. [MoleculeACE: paper and benchmark](https://doi.org/10.1021/acs.jcim.2c01073) — van Tilborg et al.: activity-cliff benchmark; source data for milestones 2–4.

5. [MoleculeACE source revision](https://github.com/molML/MoleculeACE/tree/7e6de0bd2968c56589c580f2a397f01c531ede26/MoleculeACE/Data/benchmark_data) — Exact pinned data revision; Aster uses its own acquisition protocol.

6. [CheMeleon research paper](https://arxiv.org/abs/2506.15792) — Burns et al., Deep Learning Foundation Models from Classical Molecular Descriptors.

7. [CheMeleon checkpoint](https://zenodo.org/records/15460715) — Frozen pretrained encoder for milestones 2–3; checksum verified.

8. [Chemprop foundation-model API](https://chemprop.readthedocs.io/en/main/chemeleon_foundation_finetuning.html) — BondMessagePassing and MeanAggregation; custom observed-only adaptation in milestone 3.

9. [Efron: Bootstrap Methods (1979)](https://doi.org/10.1214/aos/1176344552) — Bootstrap resampling foundation; not a confidence guarantee for Aster disagreement.

10. [Cross-validated predictions](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.cross_val_predict.html) — Background for training-only out-of-fold residual diagnostics in milestone 4.

11. [PyTorch](https://pytorch.org/docs/stable/index.html) — Tensor execution and observed-only encoder optimization in milestones 2–3.

The posters use Aster's actual saved metrics. They do not copy third-party figures.
MoleculeACE and CheMeleon benchmark/publication results are distinct from Aster's
retrospective acquisition experiments. No unseen-pretraining or clinical claim is made.

Milestone 1 counts threshold assay hits; milestones 2–4 count strongest-decile
pool discoveries. Their numbers are **not directly comparable across milestones**.
The milestone 3 fine-tuning comparison uses six matched cases, separate from its
24-case frozen-transfer comparison. Replays are correlated; no target-level
significance claim is implied by the bar charts.

The current default remains greedy Morgan + ridge. The latest milestone tested
reliability-aware selection, not neural tuning. The illustrated diagram is a
conceptual explanation; audited numeric evidence is in the experiment reports.
