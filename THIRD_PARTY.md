# What we did not write ourselves

## Libraries (from PyPI, see requirements.txt)
pandas, pyarrow, numpy, scikit-learn (BSD/Apache) · LightGBM (MIT) · XGBoost (Apache-2.0) · CatBoost (Apache-2.0) · joblib (BSD).
XGBoost and CatBoost are imported by the shared model module; the submitted predictions use LightGBM only.

## Data and documentation
The Decode & Detect training/test packages and README (organisers), not included in the ZIP.
Value semantics follow the organisers' README. The organisers' payments.py and starter notebook were read
for reference; the submitted code does not import them.

## Outside services and pre-trained models
None. No external labels, no pre-trained models, no API calls.

## AI assistance
Code and documentation were written with the help of Claude (Anthropic) as a coding assistant,
under the team's direction and review.
