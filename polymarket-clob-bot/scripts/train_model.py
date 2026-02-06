"""Train ML model on collected historical data."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ML prediction model")
    parser.add_argument("--data-dir", type=str, default="./data", help="Directory with training CSVs")
    parser.add_argument("--model", type=str, default="xgboost", choices=["xgboost", "lightgbm"],
                        help="Model type to train")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for model (default: data-dir)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir) if args.output_dir else data_dir

    if not data_dir.exists():
        logger.error("Data directory not found: %s", data_dir)
        sys.exit(1)

    csv_files = list(data_dir.glob("trades_*.csv"))
    if not csv_files:
        logger.error("No training CSV files found in %s", data_dir)
        logger.info("Run scripts/collect_history.py first, or accumulate trades via the bot")
        sys.exit(1)

    logger.info("Found %d training CSV files in %s", len(csv_files), data_dir)
    logger.info("Training %s model...", args.model)

    from src.ml.trainer import Trainer

    trainer = Trainer(data_dir=data_dir, output_dir=output_dir)
    result = trainer.train(model_type=args.model)

    if "error" in result:
        logger.error("Training failed: %s", result["error"])
        sys.exit(1)

    print("\n" + "=" * 50)
    print("TRAINING RESULTS")
    print("=" * 50)
    print(f"Model: {args.model}")
    print(f"Samples: {result['n_samples']}")
    print(f"Features: {result['n_features']}")
    print(f"Accuracy: {result['accuracy']:.3f}")
    print(f"Precision: {result['precision']:.3f}")
    print(f"Recall: {result['recall']:.3f}")
    print(f"AUC: {result['auc']:.3f}")
    print(f"Model saved: {result['model_path']}")
    print("\nTop features:")
    for name, importance in result.get("feature_importance", [])[:10]:
        print(f"  {name:30s} {importance:.4f}")


if __name__ == "__main__":
    main()
