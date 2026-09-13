"""Statistical data profiler and anomaly detector for SQL query results."""

from typing import Dict, Any, List
import pandas as pd


class DataResultProfiler:
    """Profiles tabular SQL results to extract descriptive statistics and statistical outliers."""

    @staticmethod
    def profile(df: pd.DataFrame) -> Dict[str, Any]:
        if df is None or df.empty:
            return {"numeric_columns": {}, "anomalies_detected": 0, "top_share_ratio": 0.0}

        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        col_stats: Dict[str, Dict[str, float]] = {}
        anomaly_count = 0
        top_share = 0.0

        for col in numeric_cols:
            series = df[col].dropna()
            if series.empty:
                continue

            mean_val = float(series.mean())
            std_val = float(series.std()) if len(series) > 1 else 0.0
            min_val = float(series.min())
            max_val = float(series.max())
            total_val = float(series.sum())

            col_stats[col] = {
                "mean": round(mean_val, 2),
                "std": round(std_val, 2),
                "min": round(min_val, 2),
                "max": round(max_val, 2),
                "sum": round(total_val, 2),
            }

            if std_val > 1e-6 and len(series) >= 3:
                z_scores = ((series - mean_val) / std_val).abs()
                anomaly_count += int((z_scores > 1.8).sum())

            if total_val > 0 and max_val > 0:
                top_share = max(top_share, round(max_val / total_val, 4))

        return {
            "numeric_columns": col_stats,
            "anomalies_detected": anomaly_count,
            "top_share_ratio": top_share,
        }
