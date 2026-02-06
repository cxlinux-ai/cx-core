"""ML predictor: load trained model and predict market outcomes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.ml.feature_engine import FEATURE_NAMES, FeatureRow

logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    """Model prediction output."""
    probability: float  # P(leader wins)
    features_used: dict[str, float]
    model_type: str = ""


class Predictor:
    """Loads a trained model and produces predictions.

    Gracefully falls back if no model is available — the strategy
    runs without ML in that case.
    """

    def __init__(self, model_dir: Path | None = None) -> None:
        self._model = None
        self._model_type = ""
        self._model_dir = model_dir or Path("data")

        self._try_load()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _try_load(self) -> None:
        """Attempt to load a trained model from disk."""
        # Try XGBoost first, then LightGBM
        for name, loader in [("xgboost", self._load_xgb), ("lightgbm", self._load_lgb)]:
            try:
                loader()
                if self._model is not None:
                    logger.info("Loaded %s model from %s", name, self._model_dir)
                    return
            except Exception:
                continue

        logger.info("No ML model found — strategy will run without ML predictions")

    def _load_xgb(self) -> None:
        import xgboost as xgb
        path = self._model_dir / "model_xgb.json"
        if path.exists():
            model = xgb.XGBClassifier()
            model.load_model(str(path))
            self._model = model
            self._model_type = "xgboost"

    def _load_lgb(self) -> None:
        import lightgbm as lgb
        path = self._model_dir / "model_lgb.txt"
        if path.exists():
            self._model = lgb.Booster(model_file=str(path))
            self._model_type = "lightgbm"

    def predict(self, feature_row: FeatureRow) -> Prediction | None:
        """Predict probability that the current market leader wins."""
        if self._model is None:
            return None

        try:
            # Build feature vector in correct order
            x = np.array([[feature_row.features.get(name, 0.0) for name in FEATURE_NAMES]])

            if self._model_type == "xgboost":
                prob = self._model.predict_proba(x)[0][1]
            elif self._model_type == "lightgbm":
                prob = self._model.predict(x)[0]
            else:
                return None

            return Prediction(
                probability=float(prob),
                features_used=dict(feature_row.features),
                model_type=self._model_type,
            )

        except Exception as exc:
            logger.debug("Prediction failed: %s", exc)
            return None
