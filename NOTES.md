# Notes: Japan pipeline (final cleaning, 15 Oct 2026)

All result numbers live in `analysis.ipynb`. Captions are computed from outputs with `caption()`, so they cannot go stale. The values quoted below are from the final Japan run.

## Final freeze rule (locked)
Documented sentinels only, with no thresholds tuned to Japan, so the rule carries over unchanged to the season.
- **(a) Freeze:** a run of unchanged Speed + RPM + nGear containing `Throttle == 104`, plus a 1-sample buffer. Sectors and segments that overlap a freeze are dropped and logged; segments whose peak is their first sample are also dropped. 104 during running is our observation (FastF1 documents it for stationary cars). The same freeze appears in OpenF1, so it originates upstream of FastF1.
- **(c) Brake unknown:** OpenF1 `brake == 104`. These samples do not end a full-throttle segment and are trimmed from a segment's end.
- **(d) Genuine brake:** OpenF1 `brake == 100` at full throttle is left as is.
- **(e) Implausible acceleration** (single-step increase >= 5 km/h above P/(m v), with P = 800 kW, m = 700 kg and drag ignored): **not a filter.** A segment gets `JumpFlag` if a jump lies in [first peak-speed sample − 1, segment end]. Key results are reported with and without flagged segments (Section 11, following Steegen et al. 2016). In Japan only STR lap 8 T14→T16 is flagged.
- **(b) Speed/RPM ratio check:** rejected. It does not separate stale from updating Speed, so it is kept only as a diagnostic (Section 3.5).

## OpenF1 input
- OpenF1 brake values are a pipeline input. Each driver's `car_data` is downloaded once per session and cached in `cache/openf1/` (gitignored).
- Without OpenF1 data, brake is taken at face value, and `run_session` records `brake_source = "no OpenF1: brake taken at face value"` in the QC summary.
- The FastF1-only substitute was removed. It caught 65 of 75 sentinel samples, with 22 false positives (Appendix A3).
- **Season run:** the OpenF1 `session_key` must be looked up for each qualifying session (not implemented; Japan is hard-coded as `OPENF1_SESSION = 11249`).

## Other decisions
- **Push laps:** `pick_wo_box()`, `pick_quicklaps()` (107 %), `pick_not_deleted()`. The deleted lap (track limits at T13, Spoon) is excluded because it affects exit speed onto the back straight.
- **Lap selection:** per driver and per sector or straight, the latest quali part with a clean lap first, then the fastest lap within it. `QualiPart` is stored on every row.
- **Main straight:** stitched across the timing line (±30 s of whole-session car data); flagged `CrossesTimingLine` (FIA C5.2.2) and reported separately.
- **Straight labels:** named after the corner a segment ends at, matched by X/Y. FastF1's corner `Distance` column is not used, because it is computed from `laps.pick_fastest()`.
- **Validation 2 (130R = T15):** primary window = peak before T15 → minimum to T15 + 100 m (pre-specified); sensitivity window = peak → segment end. F1Technical is an approximate reference, not ground truth.
- **Sector PKE:** partial replication of Bopaiah & Samuel (2021), with coverage stated.
- **Gradient:** comparisons within a straight are unaffected by gradient (the same for all cars); comparisons across straights are not.
- **PU mapping:** verified against The Race. Figures are exported as PDF to `figures/`.

## Limitations
- Implausible jumps before the peak do not affect clip_delta or decel_rate (peak → end), but they do affect segment and sector PKE (secondary metric).
- 291 implausible jumps occur on push laps, mostly within 300 m after a corner. They are a data-quality finding that adds noise to individual readings.
- One or two cars per team, one lap each: comparisons are descriptive, not estimates of team or PU effects.

## Deviations from spec
- **Validation 2 wording:** "first braking sample" became "last full-throttle sample before the driver lifts or brakes" (what the code does).
- **Segers page ranges:** section 3.6 runs to p.75; the braking-point sentence is on p.105 (not cited, because we do not use longitudinal acceleration).
- **Figures:** the strip plots spread tied values deterministically with one label per tie. The map uses three accent colours for the straights, shared with the taper figure.
- **Numbering:** tables and figures are numbered automatically in order, so the planned "Figure 3b" is Figure 5.
- **Not cited:** the FastF1 "Known bugs" page returns 404.
- **Warning filter:** one numpy timedelta `DeprecationWarning`, raised inside pandas/FastF1, is silenced by its exact message.

## Season run (first pass, 14 Oct 2026)
- **Calendar:** the 2026 Bahrain and Saudi Arabian GPs were cancelled (OpenF1 `is_cancelled` for Sakhir and Jeddah). The Bahrain GP was rescheduled to Sepang (OpenF1 session 11730, location "Kuala Lumpur"), and FastF1 correctly lists it as "Bahrain Grand Prix".
- **Missing circuit info:** FastF1 has no circuit info (corner positions, from the MultiViewer API) for Madrid and Sepang, and `Session.get_circuit_info()` then fails with an `AttributeError` (known: FastF1 issue #692).
  - `run_session` now skips corner-labelled straights for such sessions and logs `circuit_info = "no corner positions in FastF1: labelled straights skipped"`. Sectors/PKE, main-straight rows, freeze share, the distance check and exclusions are still produced. Japan is unchanged.
  - Madrid has no main-straight rows: its full-throttle stretch over the line is 420–475 m, below the 500 m minimum.
- **Reporting rule:** a straight is reported for a session only with >= 10 clean drivers (`MIN_CLEAN_DRIVERS` in `02_season.ipynb`).

## Next steps
- **Data-driven straight labelling** as a fallback for venues without FastF1 circuit info: cluster segment end positions (X/Y lap position) across drivers and label each cluster by its median end position, instead of the next corner.
- **Lap-level data checks (implemented):** `dead_lap_reason` rejects a push lap and logs it if Speed is zero for the whole lap, X/Y is (0, 0) on any sample, or X/Y is stationary for the whole lap. No thresholds.
  - *Deviation:* "X/Y stationary on any sample" would have rejected 126 laps, 102 of them in China, because repeated position samples are normal there (median 4 per affected lap). So the condition is "stationary for the whole lap".
  - The rule rejects 2 laps in the season: Hungary COL lap 2 (dead) and Miami HUL lap 2 (X/Y (0, 0)).
  - The 3 % car-vs-X/Y distance check stays as QC only. It flags 43 of 1,518 push laps, but 35 selected rows come from those laps, and most of their error comes from a freeze elsewhere on the lap rather than in the selected segment.
- **"Lap end" segments (implemented):** a segment with no corner ahead within its lap is truncated by the lap boundary. At Monza these are the Parabolica-to-line stretch on laps where the driver lifted at the line; the main straight is measured across the line separately. Japan is unchanged by both rules.
- **Madrid and Sepang** are included with what they contribute (sectors and, for Sepang, the main straight), with the reasons logged.

## Open issues
1. **Validation 2:** the primary window is about 11.6 km/h (mean drop difference) from F1Technical; the segment-end window is about 2.5 km/h. F1Technical's source, driver and lap per team, and minimum-speed location are unknown. On raw fastest laps, both windows are far off (15–25 km/h), because 8 of 12 raw laps contain freezes in T14–T16.
2. **The 15 isolated `Throttle == 104` samples** are flagged but not inspected.
3. **Unverified per-event inputs:** reduced energy limits, the 50 kW/s ramp, and post-Miami amendments are not in `refs/`. C5.2.8 is "subject to Article B7.2.1" (Section B, not in `refs/`).
4. **Untested on other events:** `run_session` has only been run on Japan. Other events need their official circuit length (Validation 1) and an OpenF1 session key; Validation 2 is Japan-specific.
5. **Map label:** the corner 11 label slightly touches the T12→T13 line in the map figure.
6. **Steegen et al. (2016):** the PDF is still to be added to `refs/`.
