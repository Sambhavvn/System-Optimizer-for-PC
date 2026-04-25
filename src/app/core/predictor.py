from __future__ import annotations
import pandas as pd
from .logger import logger

class PerformancePredictor:
    """
    This is a simple mock ML model.
    Later you can add real machine learning to predict system slowdown,
    thermal throttling, or suggest performance modes.
    """

    def __init__(self):
        self.is_trained = False
        logger.info("📌 PerformancePredictor initialized (mock mode).")

    def train(self, df: pd.DataFrame) -> bool:
        """
        Trains the model with system data.
        Minimum 50 rows are required for meaningful training.
        """
        if df is None or df.empty or len(df) < 50:
            logger.info("⚠ Not enough data to train ML model.")
            return False

        logger.info(f"✅ Training mock model on {len(df)} data points...")
        self.is_trained = True
        return True

    def predict(self, cpu_usage: float, temperature: float) -> str:
        """
        Mock prediction logic.
        You can replace this with real ML model later using scikit-learn or TensorFlow.
        """
        if not self.is_trained:
            return "Model not trained"

        if cpu_usage > 85 or temperature > 80:
            return "High Risk of Throttling"
        else:
            return "System Stable"
