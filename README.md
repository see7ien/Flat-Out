# F1 2026 Clipping Analysis

A reproducible, season-wide measurement of full-throttle speed loss ("clipping") in 2026 F1 qualifying from FastF1 telemetry, compared across power unit manufacturers.

## Repository
| Path | Contents |
|---|---|
| `flatout.py` | Pipeline module: constants (with citations), telemetry freeze flags, OpenF1 brake input, push-lap selection, sector PKE, full-throttle segments and clipping metrics, `run_session()`, `openf1_session_key()`, `caption()` |
| `01_japan_validation.ipynb` | 2026 Japanese GP: validation, freeze evidence, results, robustness check, appendices |
| `02_season.ipynb` | Season run: every 2026 main Qualifying session through `run_session()`, with a QC summary |
| `figures/` | Figures exported as PDF |
| `NOTES.md` | Decisions, deviations from spec, open issues |
| `requirements.txt` | Python dependencies |

Not tracked (see `.gitignore`): `cache/` (FastF1 and OpenF1 downloads), `data/` (output CSVs), `refs/` (reference PDFs).

## How to run
```bash
python -m venv venv
```
```bash
venv/Scripts/pip install -r requirements.txt
```
Then open the notebooks from the repository root:
- `01_japan_validation.ipynb` writes `data/japan_sectors.csv`, `data/japan_segments.csv` and the figures.
- `02_season.ipynb` writes one set of CSVs per session to `data/season/`, plus `data/season/qc_summary.csv`.

The first run downloads FastF1 sessions and OpenF1 `car_data` (about 16,000 rows per driver per session) into `cache/`; later runs read from the cache.

One session from Python:
```python
from flatout import openf1_session_key, run_session
tables, qc = run_session(2026, "Japan", official_length_m=5807, openf1_session=openf1_session_key(2026, "Japan"))
```
