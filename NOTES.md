# Notes: Japan pipeline (13–14 Oct 2026)

## Decisions
- **Freeze definition:** a run of unchanged Speed + RPM + nGear is a freeze if it contains `Throttle == 104`, or Brake = True with Throttle >= 98. The second case is the sentinel in the brake channel: OpenF1 shows `brake == 104` with `throttle == 100` on STR lap 8 (Table A2). A 1-sample buffer is added on each side. 104 during running is our observation (FastF1 documents it for stationary cars). The same freeze appears in OpenF1, so it originates upstream of FastF1.
- **Brake is unreliable inside a freeze:** OpenF1 reports `brake == 104`, which FastF1 casts to `True`.
- **Pipeline order:** flag freezes first, then detect full-throttle segments (Throttle >= 98, Brake off, single-sample dips merged, >= 500 m). Any sector or segment overlapping a freeze is dropped and logged, as is any segment whose peak is its first sample (start truncated).
- **Push laps:** `pick_wo_box()`, `pick_quicklaps()` (107 %), `pick_not_deleted()`. The single deleted lap (track limits at T13, Spoon) stays excluded, because it affects exit speed onto the back straight.
- **Lap selection:** per driver, per sector or straight, the latest quali part with a clean lap first, then the fastest lap within it. `QualiPart` is stored on every row.
- **Main straight:** stitched across the timing line (±30 s of whole-session car data) and kept only if freeze-free on both sides. Flagged `CrossesTimingLine` (FIA C5.2.2: energy is accounted per lap at the timing line) and reported separately.
- **Straight labels:** each straight is named after the corner it ends at, matched by X/Y. FastF1's corner `Distance` column is not used, because it is computed from `laps.pick_fastest()`, which here is ANT's frozen lap.
- **Validation 2 (130R = T15):** pre-specified primary window = peak before T15 → minimum to T15 + 100 m. Sensitivity window = peak → segment end. F1Technical is an approximate reference, not ground truth.
- **Sector PKE:** kept as a partial replication of Bopaiah & Samuel (2021), with coverage stated; no rescue attempts.
- **PU mapping:** verified against The Race. **Notebook:** edited directly; the builder script is retired.

## Deviations from spec
- **Validation 2 wording:** "first braking sample" became "last full-throttle sample before the driver lifts or brakes" (what the code does). "Correspond to" became "closest to" (what Table 13 shows).
- **vmax_position:** reported as measured, not as 0.5: mean 0.50 (median 0.51, n = 20) after the brake-sentinel rule; 0.48 before it.
- **Segers page ranges:** section 3.6 runs to p.75, not p.74. The braking-point sentence is on p.105; pp.104–105 is not cited, because we do not use longitudinal acceleration.
- **Figure 3:** tied values are spread deterministically with one label per tie, instead of random jitter.
- **Map (Figure 4):** the three straights use three accent colours (shared with Figure 5) instead of one.
- **Known-bugs page:** the FastF1 "Known bugs" page returns 404; not cited.
- **Warning filter:** one numpy timedelta `DeprecationWarning`, raised inside pandas/FastF1, is silenced by its exact message.

## Open issues
1. **The brake-sentinel rule may over-flag.** As specified, any Brake = True sample at full throttle seeds a freeze, even a 1-sample run. That flags all 167 such samples (on 70 of 108 push laps), not only the 45 inside unchanged runs.
   - Coverage drops: sector rows 75 → 58 (full lap 16 → 6 drivers), segment rows 64 → 59, main straight 21 → 18 drivers.
   - OpenF1 confirms 104 only for STR lap 8. Whether the other samples are also 104, or real left-foot braking, is unchecked.
   - Options: check them in OpenF1, or require runs of >= 2–3 samples.
2. **STR:** T12→T13 (lap 5, clip_delta 48 km/h) is kept as a valid outlier. T14→T16 (lap 8) is now flagged and excluded; no other STR lap gives a clean T14→T16 segment. The start-truncation rule removes nothing in Japan: STR's peak repeats over 3 samples, so its `vmax_position` was 0.05, not 0.
3. **The 15 isolated `Throttle == 104` samples** are flagged but not inspected.
4. **Validation 2 mismatch:** the primary window is 11.0–13.1 km/h from F1Technical; the segment-end window is 1.6–2.2 km/h. F1Technical's source, driver and lap per team, and minimum-speed location are unknown.
5. **Unverified per-event inputs:** which events have reduced energy limits or the 50 kW/s ramp; post-Miami amendments are not in `refs/`. C5.2.8 is "subject to Article B7.2.1", which is in Section B (not in `refs/`).
6. **Untested on other events:** `run_session` has only been run on Japan. Other events need their official circuit length for Validation 1, and Validation 2 is Japan-specific.
7. **Sector PKE coverage:** S1 22, S2 15, S3 15, full lap 6 of 22 drivers; Honda has S1 and S2 (ALO only).
8. **Map label:** the corner 11 label slightly touches the T12→T13 line in Figure 4.
