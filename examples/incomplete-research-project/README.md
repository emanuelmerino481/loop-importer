# Synthetic Response Classifier — work in progress

This is a deliberately incomplete, synthetic research project used to demonstrate project import. It does not contain real patient, biological, or proprietary data.

Current notes:

- Try a larger hidden layer and mixed precision.
- Validation accuracy looked better in the latest run, but the primary metric is not frozen.
- `seed: 42` appears in the current config; an older result uses seed 7.
- The exact train/validation split and formal baseline still need confirmation.
- TODO: decide whether `results/metrics_seed42.json` is the reportable result.

Possible commands found in old notes:

```bash
python scripts/prepare_data.py --input data/raw/sample.csv
python scripts/train.py --config configs/experiment.yaml
python scripts/evaluate.py --checkpoint checkpoints/model_seed42.ckpt
python scripts/report.py --results results/
```

These commands are documentary evidence only. The importer must not execute them.
