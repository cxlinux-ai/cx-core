"""Offline training pipeline for the ML prediction model."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit

from src.ml.feature_engine import FEATURE_NAMES

logger = logging.getLogger(__name__)


class Trainer:
    """Trains an XGBoost or LightGBM classifier on historical trade data."""

    def __init__(self, data_dir: Path, output_dir: Path | None = None) -> None:
        self._data_dir = data_dir
        self._output_dir = output_dir or data_dir

    def train(self, model_type: str = "xgboost") -> dict:
        """Train a model on historical CSV data.

        Args:
            model_type: "xgboost" or "lightgbm"

        Returns:
            Dict with metrics and model path.
        """
        df = self._load_data()
        if df is None or len(df) < 50:
            logger.error("Insufficient training data (%d rows)", len(df) if df is not None else 0)
            return {"error": "Insufficient data"}

        # Prepare features and labels
        feature_cols = [c for c in FEATURE_NAMES if c in df.columns]
        if not feature_cols:
            logger.error("No matching feature columns found in data")
            return {"error": "No features"}

        X = df[feature_cols].fillna(0).values
        y = df["label"].values

        # Time-series split (no lookahead)
        tscv = TimeSeriesSplit(n_splits=5)
        metrics_list: list[dict] = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            if model_type == "xgboost":
                model, fold_metrics = self._train_xgb(X_train, y_train, X_test, y_test)
            else:
                model, fold_metrics = self._train_lgb(X_train, y_train, X_test, y_test)

            fold_metrics["fold"] = fold
            metrics_list.append(fold_metrics)
            logger.info("Fold %d: acc=%.3f auc=%.3f", fold, fold_metrics["accuracy"], fold_metrics["auc"])

        # Train final model on all data
        if model_type == "xgboost":
            final_model, _ = self._train_xgb(X, y, X, y)
            model_path = self._output_dir / "model_xgb.json"
            final_model.save_model(str(model_path))
        else:
            final_model, _ = self._train_lgb(X, y, X, y)
            model_path = self._output_dir / "model_lgb.txt"
            final_model.save_model(str(model_path))

        # Feature importance
        if model_type == "xgboost":
            importance = dict(zip(feature_cols, final_model.feature_importances_))
        else:
            importance = dict(zip(feature_cols, final_model.feature_importance()))

        sorted_importance = sorted(importance.items(), key=lambda x: x[1], reverse=True)

        # Average metrics across folds
        avg_metrics = {
            "accuracy": np.mean([m["accuracy"] for m in metrics_list]),
            "precision": np.mean([m["precision"] for m in metrics_list]),
            "recall": np.mean([m["recall"] for m in metrics_list]),
            "auc": np.mean([m["auc"] for m in metrics_list]),
            "model_path": str(model_path),
            "feature_importance": sorted_importance[:10],
            "n_samples": len(df),
            "n_features": len(feature_cols),
        }

        logger.info(
            "Training complete: acc=%.3f auc=%.3f samples=%d model=%s",
            avg_metrics["accuracy"], avg_metrics["auc"], len(df), model_path,
        )

        # Save feature importance report
        report_path = self._output_dir / "feature_importance.txt"
        with open(report_path, "w") as f:
            f.write("Feature Importance Report\n")
            f.write("=" * 40 + "\n")
            for name, imp in sorted_importance:
                f.write(f"{name:30s} {imp:.4f}\n")
            f.write(f"\nAccuracy: {avg_metrics['accuracy']:.3f}\n")
            f.write(f"AUC: {avg_metrics['auc']:.3f}\n")
            f.write(f"Samples: {avg_metrics['n_samples']}\n")

        return avg_metrics

    def _load_data(self) -> pd.DataFrame | None:
        """Load and concatenate all training CSVs from data directory."""
        csv_files = sorted(self._data_dir.glob("trades_*.csv"))
        if not csv_files:
            logger.warning("No training CSV files found in %s", self._data_dir)
            return None

        dfs: list[pd.DataFrame] = []
        for f in csv_files:
            try:
                df = pd.read_csv(f)
                dfs.append(df)
            except Exception as exc:
                logger.warning("Failed to read %s: %s", f, exc)

        if not dfs:
            return None

        combined = pd.concat(dfs, ignore_index=True)
        combined.sort_values("timestamp", inplace=True)

        # Create binary label: 1 = trade was profitable (leader won)
        if "outcome" in combined.columns:
            combined["label"] = (combined["outcome"] == "WIN").astype(int)
        elif "pnl" in combined.columns:
            combined["label"] = (combined["pnl"] > 0).astype(int)
        else:
            logger.error("No 'outcome' or 'pnl' column in training data")
            return None

        return combined

    @staticmethod
    def _train_xgb(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> tuple:
        import xgboost as xgb

        model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            use_label_encoder=False,
            random_state=42,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "auc": roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else 0.0,
        }
        return model, metrics

    @staticmethod
    def _train_lgb(
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> tuple:
        import lightgbm as lgb

        train_data = lgb.Dataset(X_train, label=y_train)
        valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
            "seed": 42,
        }

        model = lgb.train(
            params,
            train_data,
            num_boost_round=200,
            valid_sets=[valid_data],
        )

        y_prob = model.predict(X_test)
        y_pred = (y_prob > 0.5).astype(int)

        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "auc": roc_auc_score(y_test, y_prob) if len(set(y_test)) > 1 else 0.0,
        }
        return model, metrics
