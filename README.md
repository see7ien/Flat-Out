# Flat Out: clipping in 2026 F1 qualifying

The 2026 cars get far more of their power from the battery, and the rules cut that electrical power as speed rises above 290 km/h. One result is "clipping": a car stops accelerating, or even slows, before the end of a straight while the driver still has the throttle fully open. I wanted to see how often that actually happens, so this project measures it in every 2026 qualifying session up to Singapore, using only public telemetry, and compares the same straights with 2025.

TLDR: most 2026 cars peak before the end of the straight, the differences between engine manufacturers are about the size of the gap between teammates, and on all 33 matched straights where clipping shows up, the 2026 cars peak earlier and lose more speed than the 2025 cars did. The full write-up is in [`report/final report.pdf`](report/final%20report.pdf).

## What's in here

| Path | What it is |
|---|---|
| `report/final report.pdf` | The paper |
| `report/main.tex`, `report/refs.bib`, `report/figures/` | LaTeX source for the paper |
| `flatout.py` | The pipeline: loading sessions, flagging frozen telemetry, picking push laps, finding full-throttle segments and measuring the speed loss |
| `01_japan_validation.ipynb` | Suzuka 2026, where the method was built and checked |
| `02_season.ipynb` | Every 2026 qualifying session run through the same pipeline |
| `03_regulations.ipynb` | 2025 against 2026 at the same circuits, straight by straight (needs `02` first) |
| `04_sensitivity.ipynb` | Reruns the headline numbers with different throttle thresholds and minimum straight lengths |

A few things aren't tracked because they're large or easy to regenerate: `cache/` (FastF1 and OpenF1 downloads), `data/` (the CSV outputs), `figures/` (every figure the notebooks save; the ones used in the paper are in `report/figures/`) and `refs/` (reference PDFs).

## Running it

Set up a virtual environment and install the dependencies:

```bash
python -m venv venv
```

```bash
venv/Scripts/pip install -r requirements.txt
```

Then run the notebooks in order from the repository root. The first run downloads every session from FastF1 and OpenF1 into `cache/`, so it takes a while; after that everything reads from the cache. `02_season.ipynb` writes its results to `data/season/`, and the later notebooks read from there.

If you only want one session, you can call the pipeline directly:

```python
from flatout import openf1_session_key, run_session
tables, qc = run_session(2026, "Japan", official_length_m=5807, openf1_session=openf1_session_key(2026, "Japan"))
```

## Data

Telemetry comes from [FastF1](https://docs.fastf1.dev) (version 3.8.3), with brake data cross-checked against [OpenF1](https://openf1.org). Neither feed includes battery or energy data, so the analysis can show where and how much speed is lost, but not which rule or strategy causes it.
