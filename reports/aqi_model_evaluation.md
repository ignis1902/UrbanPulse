# UrbanPulse AQI Model Evaluation

## Objective

Evaluate one-hour-ahead AQI predictions using historical station records.

## Evaluation results

| Station | Model | MAE | RMSE | R² | Test examples |
|---|---|---:|---:|---:|---:|
| Hadapsar IITM | Persistence baseline | 14.466 | 32.495 | 0.483 | 1760 |
| Hadapsar IITM | Tuned Random Forest | 13.818 | 28.435 | 0.604 | 1760 |
| Karve Road MPCB | Persistence baseline | 9.262 | 26.530 | 0.848 | 5643 |
| Karve Road MPCB | Tuned Random Forest | 12.728 | 27.184 | 0.841 | 5643 |

## Interpretation

Lower MAE and RMSE indicate lower prediction error. Higher R² is generally preferable.
The persistence baseline predicts that the next hour's AQI equals the current observed AQI.
Random Forest should only be selected for a station when it demonstrates a reliable improvement.

## Limitations

- Historical station data contains missing hours and long gaps.
- Evaluation results apply to the available test periods and are not a guarantee of future accuracy.
- AQI source definitions and station metadata should be verified before public release.
- This report evaluates recorded AQI values; it does not establish health outcomes or regulatory compliance.

## Files

- `aqi_model_mae_comparison.png`: model error comparison.
- `aqi_predictions_*.png`: station-level prediction plots.
- `aqi_model_metrics.csv`: numerical evaluation metrics.
- `aqi_model_predictions.csv`: predictions and observed test targets.
