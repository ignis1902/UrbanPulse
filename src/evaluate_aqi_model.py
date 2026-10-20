from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

reports = Path("reports")
metrics_path = reports / "aqi_model_metrics.csv"
predictions_path = reports / "aqi_model_predictions.csv"

if not metrics_path.exists() or not predictions_path.exists():
    raise FileNotFoundError(
        "Model output CSVs not found. Run src/train_aqi_model.py first."
    )

metrics = pd.read_csv(metrics_path)
predictions = pd.read_csv(predictions_path)

required = {
    "station", "model", "MAE", "RMSE", "R2",
    "train_examples", "validation_examples", "test_examples",
}
if not required.issubset(metrics.columns):
    raise ValueError("The metrics CSV has an unexpected schema.")

# Comparison chart
stations = metrics["station"].unique()
x = np.arange(len(stations))
width = 0.36

fig, ax = plt.subplots(figsize=(10, 5))

for offset, model_name in [
    (-width / 2, "Persistence baseline"),
    (width / 2, "Tuned Random Forest"),
]:
    subset = (
        metrics[metrics["model"] == model_name]
        .set_index("station")
        .reindex(stations)
    )
    ax.bar(
        x + offset,
        subset["MAE"],
        width,
        label=model_name,
    )

ax.set_title("One-Hour-Ahead AQI Prediction Error")
ax.set_ylabel("MAE (AQI points)")
ax.set_xticks(x)
ax.set_xticklabels(stations, rotation=15, ha="right")
ax.legend()
fig.tight_layout()
fig.savefig(reports / "aqi_model_mae_comparison.png", dpi=160)
plt.close(fig)

# Actual-versus-predicted plots per station.
for station, group in predictions.groupby("station"):
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(
        group["target_time"],
        group["actual_aqi"],
        label="Actual AQI",
        linewidth=1.2,
    )
    ax.plot(
        group["target_time"],
        group["persistence_prediction"],
        label="Persistence prediction",
        linewidth=1,
    )
    ax.plot(
        group["target_time"],
        group["random_forest_prediction"],
        label="Random Forest prediction",
        linewidth=1,
    )
    ax.set_title(f"AQI Predictions — {station}")
    ax.set_xlabel("Target time (UTC)")
    ax.set_ylabel("AQI")
    ax.legend()
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()

    safe_station = (
        station.lower()
        .replace(" ", "_")
        .replace("/", "_")
    )
    fig.savefig(
        reports / f"aqi_predictions_{safe_station}.png",
        dpi=160,
    )
    plt.close(fig)

# Generate a report from the saved metrics.
lines = [
    "# UrbanPulse AQI Model Evaluation",
    "",
    "## Objective",
    "",
    "Evaluate one-hour-ahead AQI predictions using historical station records.",
    "",
    "## Evaluation results",
    "",
    "| Station | Model | MAE | RMSE | R² | Test examples |",
    "|---|---|---:|---:|---:|---:|",
]

for _, row in metrics.iterrows():
    lines.append(
        f"| {row['station']} | {row['model']} | "
        f"{row['MAE']:.3f} | {row['RMSE']:.3f} | "
        f"{row['R2']:.3f} | {int(row['test_examples'])} |"
    )

lines.extend([
    "",
    "## Interpretation",
    "",
    "Lower MAE and RMSE indicate lower prediction error. Higher R² is generally preferable.",
    "The persistence baseline predicts that the next hour's AQI equals the current observed AQI.",
    "Random Forest should only be selected for a station when it demonstrates a reliable improvement.",
    "",
    "## Limitations",
    "",
    "- Historical station data contains missing hours and long gaps.",
    "- Evaluation results apply to the available test periods and are not a guarantee of future accuracy.",
    "- AQI source definitions and station metadata should be verified before public release.",
    "- This report evaluates recorded AQI values; it does not establish health outcomes or regulatory compliance.",
    "",
    "## Files",
    "",
    "- `aqi_model_mae_comparison.png`: model error comparison.",
    "- `aqi_predictions_*.png`: station-level prediction plots.",
    "- `aqi_model_metrics.csv`: numerical evaluation metrics.",
    "- `aqi_model_predictions.csv`: predictions and observed test targets.",
])

(reports / "aqi_model_evaluation.md").write_text(
    "\n".join(lines) + "\n",
    encoding="utf-8",
)

print("Evaluation report generated:")
print(reports / "aqi_model_evaluation.md")
print(reports / "aqi_model_mae_comparison.png")
for station in predictions["station"].unique():
    safe_station = station.lower().replace(" ", "_").replace("/", "_")
    print(reports / f"aqi_predictions_{safe_station}.png")
