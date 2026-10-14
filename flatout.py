"""flatout: pipeline for measuring full-throttle speed loss ("clipping") in 2026 F1 qualifying from FastF1 telemetry.

Validation, freeze flags (documented sentinels only), push-lap selection, sector PKE, full-throttle segments and
clipping metrics, and run_session() for one qualifying session. Sources: FastF1 3.8.3 docs (HAC = "How to perform
calculations accurately", TEL = Telemetry API reference, fastf1/core.py); FIA 2026 Technical Regulations Section C,
Issue 12; Bopaiah & Samuel (2021), SAE 2021-01-0368; OpenF1 API (openf1.org).
"""
import json
import urllib.request
import warnings
from pathlib import Path

import fastf1
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from IPython.display import Markdown, display

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"

fastf1.set_log_level("WARNING")
warnings.filterwarnings("ignore", message="The 'generic' unit for NumPy timedelta")  # raised inside pandas/FastF1 timedelta ops
pd.set_option("display.width", 250)
plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", "axes.spines.top": False,
                    "axes.spines.right": False, "savefig.bbox": "tight"})


# ---------------------------------------------------------------- constants
FIG = ROOT / "figures"
SENTINEL = 104            # Throttle value for "error or unavailable data" (core.py, Telemetry channels)
XY_UNIT_M = 0.1           # position X/Y are in 1/10 m (TEL)
FULL_THROTTLE = 98        # Throttle >= 98 % with Brake off (planned metric)
MIN_SEGMENT_M = 500       # minimum full-throttle segment length (planned metric)
ACC_POWER_W = 800e3       # upper bound on propulsive power: ERS-K 350 kW (FIA 2026 Tech Regs C5.2.7) + ICE ~400 kW (approx.), rounded up
ACC_MASS_KG = 700         # deliberately below any 2026 car's mass, so the acceleration bound is lenient
MIN_JUMP_KMH = 5          # (e) robustness check: only single-step Speed increases >= 5 km/h (guards against timestamp jitter)
OPENF1_CACHE = CACHE / "openf1"
PU = {  # The Race, "What engine every F1 team is using for 2026 rules"
    "Mercedes": "Mercedes", "McLaren": "Mercedes", "Williams": "Mercedes", "Alpine": "Mercedes",
    "Ferrari": "Ferrari", "Haas F1 Team": "Ferrari", "Cadillac": "Ferrari",
    "Aston Martin": "Honda", "Red Bull Racing": "Red Bull Ford", "Racing Bulls": "Red Bull Ford", "Audi": "Audi",
}
PU_COLORS = {"Mercedes": "#0072B2", "Ferrari": "#D55E00", "Red Bull Ford": "#E69F00", "Honda": "#CC79A7",
             "Audi": "#009E73"}  # Okabe-Ito, colour-blind safe; one fixed colour per PU in every figure
STRAIGHT_COLORS = {"T13": "#4477AA", "T16": "#EE6677", "T1": "#228833"}  # Tol bright; T1 = main straight
OPENF1_BRAKE = {}  # (session_key, driver number) -> OpenF1 Date/brake, filled by load_openf1_brake
CAPTION_NO = {}
FIG.mkdir(exist_ok=True)


def caption(kind, key, text):
    """Render a caption numbered by first appearance of `key` within `kind` ("Table", "Figure", "Table A", ...)."""
    n = CAPTION_NO.setdefault(kind, {}).setdefault(key, len(CAPTION_NO.get(kind, {})) + 1)
    display(Markdown(f"*{kind}{'' if ' ' in kind else ' '}{n}. {text}*"))



# ---------------------------------------------------------------- data

def load_quali(year, event):
    """Return a loaded FastF1 qualifying session, cached to cache/."""
    fastf1.Cache.enable_cache(str(CACHE))
    session = fastf1.get_session(year, event, "Q")
    session.load()
    return session

def openf1_session_key(year, event):
    """OpenF1 session_key of the event's main Qualifying session, matched on its UTC start time (FastF1 schedule), or None.
    The year's OpenF1 Qualifying sessions (/v1/sessions?year=&session_name=Qualifying) are cached in OPENF1_CACHE and
    re-downloaded once if the event is not in the cached list."""
    OPENF1_CACHE.mkdir(parents=True, exist_ok=True)
    f = OPENF1_CACHE / f"sessions_{year}_qualifying.json"
    start = fastf1.get_event(year, event).get_session_date("Qualifying", utc=True)
    for refresh in (False, True):
        if refresh or not f.exists():
            url = f"https://api.openf1.org/v1/sessions?year={year}&session_name=Qualifying"
            f.write_bytes(urllib.request.urlopen(url).read())
        ses = pd.DataFrame(json.loads(f.read_text()))
        if len(ses):
            gap = (pd.to_datetime(ses["date_start"], utc=True).dt.tz_localize(None) - start).abs()
            if gap.min() <= pd.Timedelta(hours=1):
                return int(ses.loc[gap.idxmin(), "session_key"])
    return None

def to_seconds(df):
    """LapTime as seconds (LapTime_s), for CSV output."""
    return df.assign(LapTime=df["LapTime"].dt.total_seconds()).rename(columns={"LapTime": "LapTime_s"})



# ---------------------------------------------------------------- geometry and Validation 1

def lap_pos(lap):
    """Position data padded, then sliced to the lap with interpolated edges (HAC)."""
    return lap.get_pos_data(pad=1, pad_side="both").slice_by_lap(lap, interpolate_edges=True)


def xy_cumdist(pos):
    """Cumulative X/Y path length (m) along position samples."""
    return np.r_[0, np.cumsum(np.hypot(np.diff(pos["X"]), np.diff(pos["Y"])))] * XY_UNIT_M


def lap_geometry(lap, corners):
    """X/Y lap position (m) of each position sample, their session times (s), and each corner's lap position."""
    pos = lap_pos(lap)
    xyd, pt = xy_cumdist(pos), pos["SessionTime"].dt.total_seconds().to_numpy()
    return xyd, pt, {n: xyd[np.hypot(pos.X - c.X, pos.Y - c.Y).argmin()] for n, c in corners.iterrows()}


def position_at(xyd, pt, times):
    """Lap position (X/Y m) at each session time in `times`, via the nearest position sample (no interpolation)."""
    t = times.dt.total_seconds().to_numpy()
    return xyd[np.abs(pt[:, None] - t[None, :]).argmin(axis=0)]


def lap_distance_check(laps, official_m):
    """Validation 1: distance of each lap from car data and from X/Y, with % error vs the official length."""
    v = pd.DataFrame([dict(Driver=d, PU=PU[lap["Team"]],
                           CarData_m=lap.get_car_data().add_distance()["Distance"].iloc[-1],
                           XY_m=xy_cumdist(lap_pos(lap))[-1])
                      for d, lap in laps.items()]).set_index("Driver")
    for c in ["CarData", "XY"]:
        v[f"{c}_err%"] = 100 * (v[f"{c}_m"] / official_m - 1)
    return v



# ---------------------------------------------------------------- freezes, OpenF1 brake, implausible jumps

def ratio_dev(car, exclude=None):
    """Speed/RPM deviation from this car data's own per-gear median; NaN within ±1 sample of a gear change,
    at RPM 0, outside gears 1-8, and on `exclude`d samples."""
    g = car["nGear"]
    ok = (car["RPM"] > 0) & g.between(1, 8) & (g == g.shift(1)) & (g == g.shift(-1))
    if exclude is not None:
        ok &= ~exclude
    r = (car["Speed"] / car["RPM"]).where(ok)
    return r / r.groupby(g).transform("median") - 1


def implausible_jumps(car):
    """Samples ending a single-step Speed increase >= MIN_JUMP_KMH whose acceleration exceeds ACC_POWER_W / (ACC_MASS_KG * v),
    with v the speed before the step (m/s)."""
    dv = car["Speed"].diff()
    dt = car["SessionTime"].dt.total_seconds().diff()
    v0 = car["Speed"].shift() / 3.6
    return (dv >= MIN_JUMP_KMH) & ((dv / 3.6) / dt > ACC_POWER_W / (ACC_MASS_KG * v0))


def freeze_mask(car):
    """Frozen samples: runs of unchanged Speed+RPM+nGear containing the documented sentinel Throttle == 104.
    Returns (flagged incl. 1-sample buffer, core runs without buffer, run id)."""
    k = ["Speed", "RPM", "nGear"]
    run_id = car[k].ne(car[k].shift()).any(axis=1).cumsum()
    core = run_id.isin(run_id[car["Throttle"] == SENTINEL])
    return core | core.shift(1, fill_value=False) | core.shift(-1, fill_value=False), core, run_id


def load_openf1_brake(session_key, drivers):
    """OpenF1 car_data Date/brake per driver (downloaded once, cached in OPENF1_CACHE) into OPENF1_BRAKE."""
    OPENF1_CACHE.mkdir(parents=True, exist_ok=True)
    for num in drivers:
        f = OPENF1_CACHE / f"car_data_{session_key}_{num}.json"
        if not f.exists():
            url = f"https://api.openf1.org/v1/car_data?session_key={session_key}&driver_number={num}"
            f.write_bytes(urllib.request.urlopen(url).read())
        of = pd.DataFrame(json.loads(f.read_text()))
        of["Date"] = pd.to_datetime(of["date"], format="ISO8601").dt.tz_localize(None).astype("datetime64[ns]")
        OPENF1_BRAKE[(session_key, num)] = of[["Date", "brake"]].sort_values("Date").reset_index(drop=True)


def openf1_brake(car):
    """OpenF1 brake value for each car sample (nearest within 20 ms), or None without OpenF1 coverage of `car`."""
    for (_, num), of in OPENF1_BRAKE.items():
        if num == car.driver and of["Date"].iloc[0] <= car["Date"].iloc[0] and car["Date"].iloc[-1] <= of["Date"].iloc[-1]:
            m = pd.merge_asof(car[["Date"]].astype("datetime64[ns]"), of, on="Date", direction="nearest",
                              tolerance=pd.Timedelta(milliseconds=20))
            return pd.Series(m["brake"].to_numpy(), index=car.index)
    return None


def brake_unknown(car):
    """Brake samples carrying the 104 sentinel in OpenF1. Without OpenF1 coverage, none: brake is taken at face value."""
    ob = openf1_brake(car)
    return car["Brake"] & ob.eq(SENTINEL) if ob is not None else pd.Series(False, index=car.index)


def blocks(car, mask, end):
    """Contiguous True blocks of `mask` as (i0, i1, t0, t1), times in session seconds.
    A block lasts until the next sample, or until `end` for the last one."""
    t = np.append(car["SessionTime"].dt.total_seconds().to_numpy(), end.total_seconds())
    e = np.diff(np.r_[0, mask.to_numpy().astype(int), 0])
    i0, i1 = np.flatnonzero(e == 1), np.flatnonzero(e == -1)
    return list(zip(i0, i1, t[i0], t[i1]))


def frozen_between(lap, car, ta, tb):
    """True if a flagged freeze overlaps session time (ta, tb) in seconds."""
    return any(a < tb and b > ta for _, _, a, b in blocks(car, freeze_mask(car)[0], lap["Time"]))


def xy_path(pos, t0, t1):
    """X/Y path length (m) and elapsed time (s) between the position samples nearest t0 and t1 (no interpolation)."""
    pt = pos["SessionTime"].dt.total_seconds().to_numpy()
    a, b = np.abs(pt - t0).argmin(), np.abs(pt - t1).argmin()
    return xy_cumdist(pos.iloc[a:b + 1])[-1], pt[b] - pt[a]



# ---------------------------------------------------------------- push laps

def push_laps(session):
    """Push laps with QualiPart, and a log of excluded timed laps with reasons."""
    timed = session.laps[session.laps["LapTime"].notna()]
    part = pd.concat([l["LapNumber"].to_frame().assign(QualiPart=f"Q{i}")
                      for i, l in enumerate(session.laps.split_qualifying_sessions(), 1) if l is not None])["QualiPart"]
    reason = pd.Series("", index=timed.index)
    reason[~timed.index.isin(timed.pick_wo_box().index)] = "in/out lap"
    reason[(reason == "") & ~timed.index.isin(timed.pick_quicklaps().index)] = "slower than 107 % (cool-down/aborted)"
    reason[(reason == "") & timed["Deleted"]] = "deleted: " + timed["DeletedReason"].str.strip()
    timed = timed.assign(QualiPart=part)
    log = timed.loc[reason != "", ["Driver", "LapNumber", "QualiPart"]].assign(Reason=reason)
    return timed.loc[reason == ""], log


def corner_times(lap, numbers, corners):
    """Session time (s) of the position sample nearest each corner's X/Y."""
    pos = lap.get_pos_data(pad=1, pad_side="both")
    pt = pos["SessionTime"].dt.total_seconds().to_numpy()
    return [pt[np.hypot(pos.X - corners.loc[n, "X"], pos.Y - corners.loc[n, "Y"]).argmin()] for n in numbers]


def best_clean_lap(clean_rows, by="Driver"):
    """One row per group of already-clean rows: latest quali part first, then fastest lap within it."""
    return clean_rows.sort_values(["QualiPart", "LapTime"], ascending=[False, True]).groupby(by).head(1)



# ---------------------------------------------------------------- sectors, segments, metrics, selection

def pke(car):
    """Positive kinetic energy, eq. 4 of Bopaiah & Samuel (2021): sum(Vf^2 - Vi^2) over steps with Vf > Vi,
    divided by the interval distance x. V in m/s, x in m; result in m/s^2."""
    v = car["Speed"].to_numpy() / 3.6
    dv2 = np.diff(v ** 2)
    x = car["Distance"].iloc[-1] - car["Distance"].iloc[0]
    return dv2[dv2 > 0].sum() / x if x > 0 else np.nan


def taper_kw(v):
    """Max ERS-K power used to propel the car (kW) at speed v (km/h), outside Override Mode."""
    v = np.asarray(v, dtype=float)
    p = np.where(v < 340, 1800 - 5 * v, 6900 - 20 * v)  # FIA 2026 Tech Regs C5.2.8 i
    p = np.where(v >= 345, 0, p)                         # FIA 2026 Tech Regs C5.2.8 i
    return np.minimum(p, 350)                            # FIA 2026 Tech Regs C5.2.7 (350 kW cap)


def meta(lap):
    return dict(Driver=lap["Driver"], Team=lap["Team"], PU=PU[lap["Team"]], LapNumber=int(lap["LapNumber"]),
                QualiPart=lap["QualiPart"], LapTime=lap["LapTime"])


def full_throttle_segments(car, end):
    """(i0, i1) sample ranges of full-throttle segments >= MIN_SEGMENT_M; single-sample dips are merged.
    Brake samples with the 104 sentinel (brake_unknown) do not end a segment but are trimmed from its end."""
    unknown = brake_unknown(car).to_numpy()
    ft = (car["Throttle"] >= FULL_THROTTLE) & (~car["Brake"] | unknown)  # brake-unknown samples keep a segment open
    ft = ft | (ft.shift(1, fill_value=False) & ft.shift(-1, fill_value=False))
    d = car["Distance"].to_numpy()
    out = []
    for a, b, _, _ in blocks(car, ft, end):
        while b > a and unknown[b - 1]:
            b -= 1
        if b > a and d[b - 1] - d[a] >= MIN_SEGMENT_M:
            out.append((a, b))
    return out


SECTORS = {"S1": ("LapStartTime", "Sector1SessionTime"), "S2": ("Sector1SessionTime", "Sector2SessionTime"),
           "S3": ("Sector2SessionTime", "Sector3SessionTime"), "Full": ("LapStartTime", "Time")}


def segment_metrics(seg, jumps):
    """Clipping metrics for one segment. The peak is the last sample at maximum speed.
    JumpFlag: an implausible Speed jump (`jumps`, aligned with `seg`) lies within [first sample at peak speed - 1, segment end]."""
    sp, d = seg["Speed"].to_numpy(), seg["Distance"].to_numpy()
    k = len(sp) - 1 - np.argmax(sp[::-1])
    length, after = d[-1] - d[0], d[-1] - d[k]
    return dict(start_m=d[0], end_m=d[-1], peak_m=d[k], length_m=length,
                peak_speed=sp[k], end_speed=sp[-1], clip_delta=sp[k] - sp[-1], clip_distance=after,
                decel_rate=100 * (sp[k] - sp[-1]) / after if after > 0 else np.nan,
                vmax_position=(d[k] - d[0]) / length, taper_kw_at_peak=float(taper_kw(sp[k])), pke=pke(seg),
                JumpFlag=bool(jumps.iloc[max(int(np.argmax(sp)) - 1, 0):].any()))


def sector_segment_rows(push, corners):
    """One row per push lap and sector (PKE, Frozen) and per full-throttle segment (label, metrics, Frozen, Truncated)."""
    sec_rows, seg_rows = [], []
    for _, lap in push.iterlaps():
        car = lap.get_car_data().add_distance()
        flag = freeze_mask(car)[0]
        st = car["SessionTime"]
        for name, (a, b) in SECTORS.items():
            ta, tb = lap[a], lap[b]
            frozen = pd.isna(ta) or pd.isna(tb) or frozen_between(lap, car, ta.total_seconds(), tb.total_seconds())
            sec_rows.append(dict(meta(lap), Sector=name, Frozen=frozen,
                                 PKE=np.nan if frozen else pke(car[(st >= ta) & (st <= tb)])))

        xyd, pt, cpos = lap_geometry(lap, corners)
        jumps = implausible_jumps(car)
        for i0, i1 in full_throttle_segments(car, lap["Time"]):
            p0, p1 = position_at(xyd, pt, st.iloc[[i0, i1 - 1]])
            ahead = [n for n, x in cpos.items() if x > p1]
            seg_rows.append(dict(meta(lap), Label=f"T{min(ahead, key=cpos.get)}" if ahead else "lap end",
                                 Via=",".join(f"T{n}" for n, x in cpos.items() if p0 < x < p1),
                                 StartPos_m=p0, EndPos_m=p1, Truncated=i0 == 0 or i1 == len(car),
                                 Frozen=bool(flag.iloc[i0:i1].any()), **segment_metrics(car.iloc[i0:i1], jumps.iloc[i0:i1])))
    return pd.DataFrame(sec_rows), pd.DataFrame(seg_rows)


def line_window(session, lap, window_s=30):
    """Whole-session car data within ±window_s of the lap start, Distance = 0 at the timing line,
    and the index of the first sample after the line."""
    t_line = lap["LapStartTime"]
    car = (session.car_data[lap["DriverNumber"]]
           .slice_by_time(t_line - pd.Timedelta(seconds=window_s), t_line + pd.Timedelta(seconds=window_s)).add_distance())
    st = car["SessionTime"].dt.total_seconds()
    car["Distance"] -= np.interp(t_line.total_seconds(), st, car["Distance"])
    return car, int(np.searchsorted(st.to_numpy(), t_line.total_seconds()))


def main_straight_rows(session, push, window_s=30):
    """Full-throttle segment containing the timing line, from whole-session car data within ±window_s of each push
    lap's start. Distances are relative to the line; Status says whether the segment is usable."""
    rows = []
    for _, lap in push.iterlaps():
        car, k = line_window(session, lap, window_s)
        hit = [(a, b) for a, b in full_throttle_segments(car, car["SessionTime"].iloc[-1]) if a < k < b]
        if not hit:
            rows.append(dict(meta(lap), Status="no full-throttle segment across the line"))
            continue
        a, b = hit[0]
        m = segment_metrics(car.iloc[a:b], implausible_jumps(car).iloc[a:b])
        status = ("cut by ±30 s window" if a == 0 or b == len(car)
                  else "overlaps freeze" if freeze_mask(car)[0].iloc[a:b].any()
                  else "start truncated (peak at first sample)" if m["vmax_position"] == 0 else "ok")
        rows.append(dict(meta(lap), Status=status, **m))
    return pd.DataFrame(rows)


def segment_reason(seg_all):
    """Why each detected straight segment is unusable ("" = usable)."""
    return np.select([seg_all.Frozen, seg_all.Truncated, seg_all.vmax_position == 0],
                     ["overlaps freeze", "truncated by lap boundary", "start truncated (peak at first sample)"], "")


def select_clean(sec_all, seg_all, ms_all, exclude_jumps=False):
    """Best clean lap per driver for each sector, straight and the main straight (latest quali part, then fastest).
    With exclude_jumps, JumpFlag segments also count as unusable (robustness check, Section 11).
    Returns sectors, straights, main straight, and straights + main straight combined."""
    ok_seg, ok_main = segment_reason(seg_all) == "", ms_all.Status == "ok"
    if exclude_jumps:
        ok_seg &= ~seg_all.JumpFlag
        ok_main &= ~ms_all.JumpFlag.eq(True)  # NaN (no segment) counts as unflagged
    sectors = best_clean_lap(sec_all[~sec_all.Frozen], by=["Driver", "Sector"])
    straights = best_clean_lap(seg_all[ok_seg], by=["Driver", "Label"])
    main = best_clean_lap(ms_all[ok_main]).assign(Label="T1", Via="timing line", CrossesTimingLine=True)
    return sectors, straights, main, pd.concat([straights.assign(CrossesTimingLine=False), main], ignore_index=True)



# ---------------------------------------------------------------- figures

def strip_plot(d, path):
    """clip_delta per driver by PU (one fixed colour per PU); tied values spread side by side with one label."""
    order = list(PU_COLORS)
    tie = d.groupby(["PU", "clip_delta"])
    x = d.PU.map(order.index) + 0.12 * (tie.cumcount() - (tie.Driver.transform("size") - 1) / 2)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.scatter(x, d.clip_delta, c=d.PU.map(PU_COLORS), s=30, zorder=3)
    for (pu, val), g in tie:
        ax.annotate(", ".join(g.Driver), (x[g.index].max(), val), xytext=(5, 0), textcoords="offset points", fontsize=7, va="center")
    ax.set_xticks(range(len(order)), order)
    for t, pu in zip(ax.get_xticklabels(), order):
        t.set_color(PU_COLORS[pu])
    ax.set(xlim=(-0.5, len(order) - 0.5), ylabel="clip_delta (km/h)")
    fig.savefig(FIG / path)
    plt.show()



# ---------------------------------------------------------------- pipeline

def run_session(year, event, official_length_m=None, openf1_session=None):
    """Validation and metrics pipeline for one qualifying session. Returns (tables, qc summary dict).
    With openf1_session, brake-unknown samples come from OpenF1; otherwise brake is taken at face value (logged in qc)."""
    ses = load_quali(year, event)
    if openf1_session is not None:
        load_openf1_brake(openf1_session, ses.drivers)
    crn = ses.get_circuit_info().corners.set_index("Number")
    fl = {d: lap for d in ses.results["Abbreviation"] if (lap := ses.laps.pick_drivers(d).pick_fastest()) is not None}
    v1_ = lap_distance_check(fl, official_length_m) if official_length_m else None
    push_, lap_log_ = push_laps(ses)
    sec_all_, seg_all_ = sector_segment_rows(push_, crn)
    ms_all_ = main_straight_rows(ses, push_)
    sectors_, straights_, main_, segments_ = select_clean(sec_all_, seg_all_, ms_all_)
    frozen = pd.DataFrame([dict(PU=PU[lap["Team"]], FrozenPct=100 * freeze_mask(lap.get_car_data())[0].mean())
                           for _, lap in push_.iterlaps()])
    cols = ["Scope", "Driver", "LapNumber", "QualiPart", "Item", "Reason"]
    excl = pd.concat([
        lap_log_.assign(Scope="lap", Item=""),
        sec_all_[sec_all_.Frozen].assign(Scope="sector", Item=lambda x: x.Sector, Reason="overlaps freeze or missing sector time"),
        seg_all_.assign(Scope="straight", Item=seg_all_.Label, Reason=segment_reason(seg_all_)).query("Reason != ''"),
        ms_all_[ms_all_.Status != "ok"].assign(Scope="main straight", Item="T1", Reason=lambda x: x.Status),
    ])[cols]
    err = (lambda c, f: getattr(v1_[c].abs(), f)()) if v1_ is not None else (lambda c, f: np.nan)
    qc = {"brake_source": "OpenF1" if openf1_session is not None else "no OpenF1: brake taken at face value",
          "drivers": len(fl), "timed_laps": int(ses.laps["LapTime"].notna().sum()), "push_laps": len(push_),
          "lap_exclusions": len(lap_log_),
          "v1_car_mean_abs_err_pct": err("CarData_err%", "mean"), "v1_car_max_abs_err_pct": err("CarData_err%", "max"),
          "v1_xy_mean_abs_err_pct": err("XY_err%", "mean"), "v1_xy_max_abs_err_pct": err("XY_err%", "max"),
          "push_lap_frozen_pct_mean": frozen.FrozenPct.mean(),
          "sectors_computed": len(sec_all_), "sectors_dropped": int(sec_all_.Frozen.sum()), "sectors_selected": len(sectors_),
          "segments_detected": len(seg_all_), "segments_dropped": int((segment_reason(seg_all_) != "").sum()),
          "straights_selected": len(straights_), "main_straight_ok": int((ms_all_.Status == "ok").sum()),
          "main_straight_drivers": len(main_), "segment_rows": len(segments_),
          "selected_segments_jump_flagged": int(segments_.JumpFlag.sum())}
    tables = dict(v1=v1_, push=push_, sectors=sectors_, segments=segments_, exclusions=excl,
                  coverage=pd.concat({"sector": sectors_.groupby("Sector").Driver.nunique(),
                                      "straight": segments_.groupby("Label").Driver.nunique()}),
                  frozen_by_pu=frozen.groupby("PU").FrozenPct.mean())
    return tables, qc
