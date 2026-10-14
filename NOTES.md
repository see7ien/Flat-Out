# Notes: Japan pipeline (13–14 Oct 2026)

## Decisions
- **Freeze definition:** seed on `Throttle == 104`, extend over the surrounding run of unchanged Speed + RPM + nGear, add a 1-sample buffer each side. 104 during running is our observation (FastF1 documents it for stationary cars). The same freeze appears in OpenF1, so it originates upstream of FastF1.
- **Brake is unreliable inside a freeze:** OpenF1 reports `brake == 104`, which FastF1 casts to `True`.
- **Pipeline order:** flag freezes first, then detect full-throttle segments (Throttle >= 98, Brake off, single-sample dips merged, >= 500 m). Any sector or segment overlapping a freeze is dropped and logged.
- **Push laps:** `pick_wo_box()`, `pick_quicklaps()` (107 %), `pick_not_deleted()`. The single deleted lap (track limits at T13, Spoon) stays excluded, because it affects exit speed onto the back straight.
- **Lap selection:** per driver, per sector or straight, the latest quali part with a clean lap first, then the fastest lap within it. `QualiPart` is stored on every row.
- **Main straight:** stitched across the timing line (±30 s of whole-session car data) and kept only if freeze-free on both sides. Flagged `CrossesTimingLine` (FIA C5.2.2: energy is accounted per lap at the timing line) and reported separately.
- **Straight labels:** each straight is named after the corner it ends at, matched by X/Y. FastF1's corner `Distance` column is not used, because it is computed from `laps.pick_fastest()`, which here is ANT's frozen lap.
- **Validation 2 (130R = T15):** pre-specified primary window = peak before T15 → minimum to T15 + 100 m. Sensitivity window = peak → segment end. F1Technical is an approximate reference, not ground truth.
- **Sector PKE:** kept as a partial replication of Bopaiah & Samuel (2021), with coverage stated; no rescue attempts.
- **PU mapping:** verified against The Race. **Notebook:** edited directly; the builder script is retired.

## Deviations from spec
- **Validation 2 wording:** "first braking sample" became "last full-throttle sample before the driver lifts or brakes" (what the code does). "Correspond to" became "closest to" (what Table 13 shows).
- **vmax_position:** mean 0.48 (median 0.50) reported instead of 0.5.
- **Segers page ranges:** section 3.6 runs to p.75, not p.74. The braking-point sentence is on p.105; pp.104–105 is not cited, because we do not use longitudinal acceleration.
- **Figure 3:** tied values are spread deterministically with one label per tie, instead of random jitter.
- **Map (Figure 4):** the three straights use three accent colours (shared with Figure 5) instead of one.
- **Known-bugs page:** the FastF1 "Known bugs" page returns 404; not cited.
- **Warning filter:** one numpy timedelta `DeprecationWarning`, raised inside pandas/FastF1, is silenced by its exact message.

## Open issues
1. **Partial freezes without the sentinel.** On STR lap 8, Speed holds 305 km/h for about 1.6 s with Brake = True at Throttle = 100 while RPM keeps changing, then jumps to 316 km/h. Neither the freeze definition nor the 1.5 s stale-run check (Table B5) catches it. It starts STR's T14→T16 segment at its peak (PKE 0.0).
   - Across push laps: Brake = True at full throttle, not flagged, in 167 of 36,875 samples on 70 of 108 laps; 45 of these sit in short unchanged runs.
   - **Proposed rule (not implemented):** flag samples with Brake = True and Throttle >= 98 that sit inside an unchanged-Speed run of >= 3 samples, plus a 1-sample buffer. Also flag segments whose start or end is caused by such a sample, as possibly truncated. Effect on the selected segments is not yet counted. Left-foot braking at full throttle cannot be ruled out from the data.
2. **STR T12→T13** (clip_delta 48 km/h, decel_rate 15.6): channels look consistent and no stale run was found. No data fault identified.
3. **The 15 isolated `Throttle == 104` samples** are flagged but not inspected.
4. **Validation 2 mismatch:** the primary window is 11.6–13.1 km/h from F1Technical; the segment-end window is 1.6–2.5 km/h. F1Technical's source, driver and lap per team, and minimum-speed location are unknown.
5. **Unverified per-event inputs:** which events have reduced energy limits or the 50 kW/s ramp; post-Miami amendments are not in `refs/`. C5.2.8 is "subject to Article B7.2.1", which is in Section B (not in `refs/`).
6. **Untested on other events:** `run_session` has only been run on Japan. Other events need their official circuit length for Validation 1, and Validation 2 is Japan-specific.
7. **Sector PKE coverage:** S1 22, S2 20, S3 17, full lap 16 of 22 drivers; Honda has no S3 or full-lap value.
8. **Map label:** the corner 11 label slightly touches the T12→T13 line in Figure 4.
