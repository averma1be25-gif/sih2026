"""
ML Model management and inference
Handles model loading, caching, and predictions
"""

import joblib
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_PATH = os.getenv("MODEL_PATH", "flood_model.joblib")
BASELINE_THRESHOLD = 1.0  # Severity ratio threshold for "severe" classification


class FloodModel:
    """Wrapper for trained ML model with inference capabilities"""

    def __init__(self, model_path: str = MODEL_PATH):
        self.model = None
        self.features = None
        self.model_version = "v1.0"
        self.load_model(model_path)

    def load_model(self, model_path: str):
        """Load trained model from disk"""
        if Path(model_path).exists():
            try:
                data = joblib.load(model_path)
                self.model = data.get("model")
                self.features = data.get("features", [])
                logger.info(f"Loaded model from {model_path}. Features: {self.features}")
            except Exception as e:
                logger.error(f"Failed to load model: {e}. Using baseline only.")
                self.model = None
        else:
            logger.warning(f"Model file not found at {model_path}. Using baseline predictions.")
            self.model = None

    def predict(self, features_dict: Dict[str, float]) -> Tuple[float, float, str]:
        """
        Predict flood severity ratio and convert to risk score (0-100).
        
        Args:
            features_dict: Feature values for prediction
            
        Returns:
            (severity_ratio, risk_score, confidence_level)
        """
        if self.model is None:
            return self._baseline_prediction(features_dict)

        try:
            # Prepare feature vector in model's expected order
            X = np.array([[features_dict.get(f, 0.0) for f in self.features]])
            severity_ratio = self.model.predict(X)[0]
            
            # Convert severity_ratio to risk_score (0-100)
            # 0.5 -> 50%, 1.0 -> 70%, 1.5 -> 90%, 2.0+ -> 100%
            risk_score = min(100, max(0, 50 + severity_ratio * 20))
            confidence = 0.85
            
            return float(severity_ratio), float(risk_score), confidence
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return self._baseline_prediction(features_dict)

    def _baseline_prediction(self, features_dict: Dict[str, float]) -> Tuple[float, float, str]:
        """
        Simple baseline when model unavailable:
        severity_ratio = weighted average of normalized features
        """
        # Key indicators for hilly flash floods
        rainfall_recent = features_dict.get("recent_rainfall_mm", 0)
        water_level_trend = features_dict.get("water_level_change_m_per_hour", 0)
        soil_saturation = features_dict.get("soil_saturation_percent", 50)
        
        # Weighted baseline
        severity_ratio = (
            (rainfall_recent / 100.0) * 0.5 +  # Heavy rain = high severity
            max(0, water_level_trend) * 2.0 +  # Rising water = high severity
            (soil_saturation / 100.0) * 0.3    # Saturated soil = moderate increase
        )
        severity_ratio = min(2.5, max(0.1, severity_ratio))  # Cap at 2.5
        
        risk_score = min(100, max(0, 50 + severity_ratio * 20))
        confidence = 0.5
        
        return float(severity_ratio), float(risk_score), confidence

    def explain_prediction(self, features_dict: Dict[str, float]) -> Dict:
        """Get feature importance for a prediction (explainability)"""
        if self.model is None or not hasattr(self.model, 'feature_importances_'):
            return {"method": "baseline", "importance": {}}
        
        importances = pd.Series(
            self.model.feature_importances_,
            index=self.features
        ).sort_values(ascending=False)
        
        return {
            "method": "tree_based",
            "importance": importances.head(5).to_dict(),
            "top_features": importances.head(5).index.tolist()
        }


# Global model instance
_model_instance: Optional[FloodModel] = None


def get_model() -> FloodModel:
    """Get or initialize global model instance (singleton)"""
    global _model_instance
    if _model_instance is None:
        _model_instance = FloodModel()
    return _model_instance


def reload_model():
    """Force reload model (useful after retraining)"""
    global _model_instance
    _model_instance = FloodModel()
    logger.info("Model reloaded")
