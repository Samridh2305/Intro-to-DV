"""
COMP 6934 - Team 9 - Fewer Fires, Bigger Burns

Makes every figure in the report from the NFDB fire point file
(version 20260811). Run from the project folder:

    python make_figures.py

Figures go to figures/ (PDF for the report, PNG for quick viewing) and the
numbers we quote in the text are printed at the end.
"""

import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import geopandas as gpd


DATA_FILE = Path("data/NFDB_point_20260811.txt")
PROVINCES = Path("data/boundaries/ne_50m_admin_1_states_provinces.shp")
OUT = Path("figures")

# NOTE: "current_version" on the NRCan site gets replaced when they publish a
# new version. If the file you download is not 20260811 the numbers will be
# a bit different from the report.
NFDB_URL = "https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_pnt/current_version/NFDB_point_txt.zip"
NE_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_1_states_provinces.zip"

FIRST_YEAR, LAST_YEAR = 1980, 2025
BIG_FIRE_HA = 200

CAUSE_NAMES = {"N": "Lightning", "H": "Human", "U": "Unknown"}
CAUSE_COLOURS = {"Lightning": "#2a78d6", "Human": "#eb6834", "Unknown": "#8f8e88"}
LINE_COLOUR = "#2a78d6"
HIGHLIGHT = "#c0392b"
GREY = "#6b6a65"

MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#555555",
    "axes.grid": True,
    "grid.color": "#e3e3e3",
    "grid.linewidth": 0.6,
    "legend.frameon": False,
    "savefig.bbox": "tight",
    "savefig.dpi": 200,
})

# numbers that end up in the report text get collected here
notes = {}


# ---------------------------------------------------------------------------
# Loading and cleaning
# ---------------------------------------------------------------------------

def download(url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    zip_path = folder / url.rsplit("/", 1)[-1]
    print("downloading", url)
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(folder)


def get_data():
    # our copy of the 20260811 version is kept in the repo as a zip,
    # so unpack that first and only download if it is missing
    local_zip = DATA_FILE.parent / "NFDB_point_txt.zip"
    if not DATA_FILE.exists() and local_zip.exists():
        print("unpacking", local_zip)
        with zipfile.ZipFile(local_zip) as z:
            z.extract(DATA_FILE.name, DATA_FILE.parent)
    if not DATA_FILE.exists():
        download(NFDB_URL, DATA_FILE.parent)
    if not PROVINCES.exists():
        download(NE_URL, PROVINCES.parent)
    if not DATA_FILE.exists():
        raise SystemExit(f"Could not find {DATA_FILE}. The NFDB version on the website "
                         "has probably changed, see the README.")


def load_fires():
    raw = pd.read_csv(DATA_FILE, encoding="utf-8-sig", low_memory=False)
    notes["rows in file"] = len(raw)

    text_cols = ["SRC_AGENCY", "CAUSE", "CAUSE2", "FIRE_TYPE", "PRESCRIBED", "PROTZONE"]
    for col in text_cols:
        raw[col] = raw[col].astype(str).str.strip()

    # 1) study period. This also drops the 95 rows with YEAR = -999.
    df = raw[raw["YEAR"].between(FIRST_YEAR, LAST_YEAR)].copy()
    notes["rows 1980-2025"] = len(df)

    # 2) prescribed burns are planned fires, not wildfires. Agencies flag
    #    them in different columns so we check all of them.
    prescribed = (
        (df["CAUSE2"] == "H-PB")
        | df["PRESCRIBED"].isin(["PB", "1"])
        | df["FIRE_TYPE"].isin(["PB", "Prescribed Burn"])
        | (df["PROTZONE"] == "Prescribed Fire")
    )
    notes["prescribed burns removed"] = int(prescribed.sum())
    df = df[~prescribed]

    # 3) exact repeats: same agency, date, location, size and cause. The
    #    NFDBFIREID alone is not unique (some agencies reuse IDs for
    #    different fires) so we don't use it here.
    key = ["SRC_AGENCY", "YEAR", "MONTH", "DAY", "LATITUDE", "LONGITUDE", "SIZE_HA", "CAUSE"]
    dupes = df.duplicated(subset=key)
    notes["duplicate rows removed"] = int(dupes.sum())
    notes["duplicate area removed (ha)"] = df.loc[dupes, "SIZE_HA"].sum()
    df = df[~dupes]

    # 4) locations. All of Canada has a negative longitude, so a positive one
    #    is a missing minus sign (mostly NL in 2023). Anything still outside
    #    a rough box around Canada is kept for the totals but left off the map.
    flipped = df["LONGITUDE"] > 0
    notes["longitudes with sign fixed"] = int(flipped.sum())
    df.loc[flipped, "LONGITUDE"] *= -1

    inside = df["LATITUDE"].between(41, 84) & df["LONGITUDE"].between(-142, -52)
    notes["fires with impossible location"] = int((~inside).sum())
    df.loc[~inside, ["LATITUDE", "LONGITUDE"]] = np.nan

    # 5) month 0 means the start month is unknown (mostly MB 2000-2004)
    df["MONTH"] = df["MONTH"].replace(0, np.nan)
    notes["fires with unknown month"] = int(df["MONTH"].isna().sum())
    notes["area with unknown month (ha)"] = df.loc[df["MONTH"].isna(), "SIZE_HA"].sum()

    # 0 ha fires stay in: they are real reports (spot fires or never mapped).
    # They only drop out of the log-scale histogram.
    notes["fires with 0 ha"] = int((df["SIZE_HA"] == 0).sum())
    # OUT_DATE is not used anywhere, so the missing values don't matter to us
    notes["share missing OUT_DATE"] = df["OUT_DATE"].isna().mean()

    df["cause"] = df["CAUSE"].map(CAUSE_NAMES)
    notes["fires after cleaning"] = len(df)
    return df


def save(fig, name):
    OUT.mkdir(exist_ok=True)
    # no creation date in the PDF, so re-running gives the exact same file
    fig.savefig(OUT / f"{name}.pdf", metadata={"CreationDate": None})
    fig.savefig(OUT / f"{name}.png")
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------------------
# Figure 1 - fires and area per year
# ---------------------------------------------------------------------------

def fig_yearly(df):
    yearly = df.groupby("YEAR").agg(fires=("SIZE_HA", "size"), area=("SIZE_HA", "sum"))
    yearly["area_mha"] = yearly["area"] / 1e6

    early = yearly.loc[1980:1989]
    late = yearly.loc[2016:2025]
    notes["mean fires/yr 1980-89"] = early["fires"].mean()
    notes["mean fires/yr 2016-25"] = late["fires"].mean()
    notes["mean area/yr 1980-89 (Mha)"] = early["area_mha"].mean()
    notes["mean area/yr 2016-25 (Mha)"] = late["area_mha"].mean()
    notes["median area/yr (Mha)"] = yearly["area_mha"].median()
    notes["2023 area (Mha)"] = yearly.loc[2023, "area_mha"]
    notes["2025 area (Mha)"] = yearly.loc[2025, "area_mha"]
    notes["area ranking"] = list(yearly["area_mha"].sort_values(ascending=False).index[:5])

    # large fires per year - used in the text, not plotted on their own
    big_per_year = df[df["SIZE_HA"] > BIG_FIRE_HA].groupby("YEAR").size()
    notes["fires > 200 ha per yr, 1980-89"] = big_per_year.loc[1980:1989].mean()
    notes["fires > 200 ha per yr, 2016-25"] = big_per_year.loc[2016:2025].mean()
    notes["fires > 200 ha in 2023"] = int(big_per_year[2023])
    notes["fires > 200 ha in 2025"] = int(big_per_year[2025])
    notes["previous max fires > 200 ha (year, n)"] = (
        int(big_per_year.drop(2023).idxmax()), int(big_per_year.drop(2023).max()))
    y23 = df[df["YEAR"] == 2023]
    notes["2023: share of area from fires >= 10,000 ha"] = (
        y23.loc[y23["SIZE_HA"] >= 10_000, "SIZE_HA"].sum() / y23["SIZE_HA"].sum())
    notes["2023: lightning share of area"] = (
        y23.loc[y23["cause"] == "Lightning", "SIZE_HA"].sum() / y23["SIZE_HA"].sum())

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.6), sharex=True)

    ax1.plot(yearly.index, yearly["fires"], color=LINE_COLOUR, lw=1.6)
    ax1.set_ylabel("Fires reported")
    ax1.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
    ax1.set_ylim(0, 13000)
    ax1.set_title("(a) Number of wildfires per year", loc="left")

    ax2.plot(yearly.index, yearly["area_mha"], color=LINE_COLOUR, lw=1.6)
    ax2.set_ylabel("Area burned (million ha)")
    ax2.set_ylim(0, 19)
    ax2.set_title("(b) Area burned per year", loc="left")

    # decade averages at the start and end of the record. Label positions
    # are picked by hand so they sit in empty space.
    for ax, col in [(ax1, "fires"), (ax2, "area_mha")]:
        for period in (early, late):
            m = period[col].mean()
            ax.hlines(m, period.index.min(), period.index.max(), color=GREY, ls="--", lw=1.2)
    kw = dict(ha="center", va="center", fontsize=8, color=GREY)
    ax1.text(1984, 5000, f"avg {early['fires'].mean():,.0f}", **kw)
    ax1.text(2020, 3200, f"avg {late['fires'].mean():,.0f}", **kw)
    ax2.text(1985, 3.5, f"avg {early['area_mha'].mean():.1f}M ha", **kw)
    ax2.text(2019, 5.6, f"avg {late['area_mha'].mean():.1f}M ha", **kw)

    for yr in (2023, 2025):
        ax1.plot(yr, yearly.loc[yr, "fires"], "o", color=HIGHLIGHT, ms=5)
        ax2.plot(yr, yearly.loc[yr, "area_mha"], "o", color=HIGHLIGHT, ms=5)
    ax2.annotate("2023: 17.6M ha", (2023, yearly.loc[2023, "area_mha"]),
                 xytext=(2008.5, 16.5), fontsize=8, color=HIGHLIGHT,
                 arrowprops=dict(arrowstyle="-", color=HIGHLIGHT, lw=0.8))
    ax2.annotate(f"2025: {yearly.loc[2025, 'area_mha']:.1f}M ha", (2025, yearly.loc[2025, "area_mha"]),
                 xytext=(2012, 11), fontsize=8, color=HIGHLIGHT,
                 arrowprops=dict(arrowstyle="-", color=HIGHLIGHT, lw=0.8))
    for yr in (1989, 1995):
        ax2.annotate(str(yr), (yr, yearly.loc[yr, "area_mha"]), xytext=(0, 4),
                     textcoords="offset points", ha="center", fontsize=8, color=GREY)

    ax2.set_xlim(1979, 2026)
    ax2.xaxis.set_major_locator(mticker.MultipleLocator(5))
    fig.tight_layout()
    save(fig, "fig1_yearly_trend")
    return yearly


# ---------------------------------------------------------------------------
# Figure 2 - fires per year for each agency (is the drop real?)
# ---------------------------------------------------------------------------

# These three only send (almost) complete records from the late 1980s on,
# you can see the jump in figure 2. Their 1980s average is not comparable.
LATE_START = {"NL": 1985, "NS": 1987, "NB": 1989}


def fig_agencies(df):
    counts = pd.crosstab(df["YEAR"], df["SRC_AGENCY"])
    # PEI only has 55 fires in total, not worth a panel
    order = counts.sum().sort_values(ascending=False).index.drop("PE")

    fig, axes = plt.subplots(3, 4, figsize=(7, 4.6), sharex=True)
    for ax, agency in zip(axes.flat, order):
        series = counts[agency]
        ax.plot(series.index, series.values, color=LINE_COLOUR, lw=1)
        if agency in LATE_START:
            ax.axvspan(1979, LATE_START[agency] - 0.5, color="#ececec", lw=0)
            ax.set_title(f"{agency}  (from {LATE_START[agency]})", fontsize=8.5, loc="left")
        else:
            # 10-year means at either end, same idea as figure 1
            a, b = series.loc[1980:1989].mean(), series.loc[2016:2025].mean()
            ax.hlines(a, 1980, 1989, color=GREY, ls="--", lw=0.9)
            ax.hlines(b, 2016, 2025, color=GREY, ls="--", lw=0.9)
            ax.set_title(f"{agency}  ({(b - a) / a * 100:+.0f}%)", fontsize=8.5, loc="left")
            notes[f"{agency} change 1980s -> 2016-25 (%)"] = (b - a) / a * 100
        ax.set_ylim(0, None)
        ax.tick_params(labelsize=7)
        ax.yaxis.set_major_locator(mticker.MaxNLocator(3))
        ax.xaxis.set_major_locator(mticker.FixedLocator([1980, 2000, 2020]))

    fig.supylabel("Fires reported per year", fontsize=9)
    fig.tight_layout(h_pad=0.6, w_pad=0.4)
    save(fig, "fig2_agencies")

    core = [a for a in order if a not in LATE_START]
    c = counts[core].sum(axis=1)
    notes["agencies shown"] = list(order)
    notes["fires/yr 1980-89, agencies reporting since 1980"] = c.loc[1980:1989].mean()
    notes["fires/yr 2016-25, agencies reporting since 1980"] = c.loc[2016:2025].mean()


# ---------------------------------------------------------------------------
# Figure 3 - fire size distribution and running total of area
# ---------------------------------------------------------------------------

def fig_sizes(df):
    sizes = df.loc[df["SIZE_HA"] > 0, "SIZE_HA"].sort_values()
    total = df["SIZE_HA"].sum()

    big = df["SIZE_HA"] > BIG_FIRE_HA
    notes["fires > 200 ha"] = int(big.sum())
    notes["share of fires > 200 ha"] = big.mean()
    notes["share of area from fires > 200 ha"] = df.loc[big, "SIZE_HA"].sum() / total
    huge = df["SIZE_HA"] >= 10_000
    notes["fires >= 10,000 ha"] = int(huge.sum())
    notes["share of fires >= 10,000 ha"] = huge.mean()
    notes["share of area from fires >= 10,000 ha"] = df.loc[huge, "SIZE_HA"].sum() / total
    notes["share of fires < 1 ha (all fires)"] = (df["SIZE_HA"] < 1).mean()
    notes["share of area from fires < 1 ha"] = df.loc[df["SIZE_HA"] < 1, "SIZE_HA"].sum() / total

    # quarter-decade bins. The edges sit between the round numbers (0.01,
    # 0.1, 1 ...) because a lot of small fires are reported as exactly those.
    bins = 10 ** np.arange(-2.125, 6.25, 0.25)
    # a handful of fires are recorded smaller than 0.01 ha, put them in the first bar
    notes["fires recorded under 0.0075 ha"] = int((sizes < bins[0]).sum())
    hist_sizes = sizes.clip(lower=bins[0] * 1.01)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 4.6), sharex=True,
                                   gridspec_kw={"height_ratios": [1.15, 1]})
    ax1.hist(hist_sizes, bins=bins, color=LINE_COLOUR, edgecolor="white", linewidth=0.6)
    ax1.set_xscale("log")
    ax1.set_ylabel("Number of fires")
    ax1.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
    ax1.set_title("(a) How many fires of each size", loc="left")

    # running total: share of all area burned by fires up to size x
    cum_share = sizes.cumsum() / total * 100
    ax2.plot(sizes.values, cum_share.values, color=LINE_COLOUR, lw=1.6)
    ax2.set_ylabel("Cumulative % of\narea burned")
    ax2.set_xlabel("Final fire size (ha, log scale)")
    ax2.set_ylim(0, 102)
    ax2.set_xlim(bins[0], bins[-1])
    ax2.set_title("(b) Share of all area burned by fires up to that size", loc="left")
    ax2.xaxis.set_major_locator(mticker.LogLocator(base=10, numticks=12))
    ax2.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x:,.0f}" if x >= 1 else f"{x:g}"))

    for ax in (ax1, ax2):
        ax.axvline(BIG_FIRE_HA, color=HIGHLIGHT, lw=1, ls="--")
    ax1.text(BIG_FIRE_HA * 1.4, ax1.get_ylim()[1] * 0.85,
             f"{notes['share of fires > 200 ha']*100:.1f}% of fires\nare over {BIG_FIRE_HA} ha",
             color=HIGHLIGHT, fontsize=8, va="top")
    below = 100 - notes["share of area from fires > 200 ha"] * 100
    ax2.text(BIG_FIRE_HA / 1.4, 55,
             f"fires up to {BIG_FIRE_HA} ha add up to\nonly {below:.1f}% of all area burned",
             color=HIGHLIGHT, fontsize=8, ha="right")

    fig.tight_layout()
    save(fig, "fig3_size_distribution")


# ---------------------------------------------------------------------------
# Figure 4 - share of fires vs share of area, by cause
# ---------------------------------------------------------------------------

def fig_causes(df):
    by_cause = df.groupby("cause").agg(fires=("SIZE_HA", "size"), area=("SIZE_HA", "sum"))
    shares = by_cause / by_cause.sum() * 100
    shares = shares.loc[["Lightning", "Human", "Unknown"]]

    big = df[df["SIZE_HA"] > BIG_FIRE_HA]
    for cause in shares.index:
        notes[f"{cause}: % of fires"] = shares.loc[cause, "fires"]
        notes[f"{cause}: % of area"] = shares.loc[cause, "area"]
        notes[f"{cause}: % of fires > 200 ha"] = (big["cause"] == cause).mean() * 100
        notes[f"{cause}: median size (ha)"] = df.loc[df["cause"] == cause, "SIZE_HA"].median()

    fig, ax = plt.subplots(figsize=(7, 2.6))
    y = np.arange(len(shares))[::-1]
    h = 0.36
    for i, cause in enumerate(shares.index):
        col = CAUSE_COLOURS[cause]
        f, a = shares.loc[cause, "fires"], shares.loc[cause, "area"]
        ax.barh(y[i] + h / 2, f, height=h, color=col, alpha=0.35, edgecolor=col, lw=0.8)
        ax.barh(y[i] - h / 2, a, height=h, color=col)
        ax.text(f + 0.8, y[i] + h / 2, f"{f:.1f}% of fires", va="center", fontsize=8)
        ax.text(a + 0.8, y[i] - h / 2, f"{a:.1f}% of area burned", va="center", fontsize=8)

    ax.set_yticks(y)
    ax.set_yticklabels(shares.index)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Percent of all wildfires, 1980-2025")
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", length=0)

    legend = [Rectangle((0, 0), 1, 1, color="#888888", alpha=0.35, ec="#888888"),
              Rectangle((0, 0), 1, 1, color="#888888")]
    ax.legend(legend, ["share of fires (light)", "share of area burned (solid)"],
              loc="lower right", fontsize=8)
    fig.tight_layout()
    save(fig, "fig4_cause_shares")


# ---------------------------------------------------------------------------
# Figure 5 - map of large fires
# ---------------------------------------------------------------------------

def fig_map(df):
    provinces = gpd.read_file(PROVINCES)
    canada = provinces[provinces["admin"] == "Canada"].to_crs(epsg=3978)

    big = df[(df["SIZE_HA"] > BIG_FIRE_HA) & df["LATITUDE"].notna()].copy()
    pts = gpd.GeoDataFrame(
        big, geometry=gpd.points_from_xy(big["LONGITUDE"], big["LATITUDE"]), crs="EPSG:4326"
    ).to_crs(epsg=3978)
    # draw the biggest fires first so the small ones are not hidden under them
    pts = pts.sort_values("SIZE_HA", ascending=False)

    def dot_size(ha):
        return np.sqrt(ha) / 12

    fig, ax = plt.subplots(figsize=(7, 5.6))
    canada.plot(ax=ax, color="#f4f3ef", edgecolor="#9d9c96", linewidth=0.5)
    for cause in ["Lightning", "Human", "Unknown"]:
        sub = pts[pts["cause"] == cause]
        ax.scatter(sub.geometry.x, sub.geometry.y, s=dot_size(sub["SIZE_HA"]),
                   color=CAUSE_COLOURS[cause], alpha=0.45, linewidths=0)

    # cut the map off a bit north of the northernmost big fire, the arctic
    # islands have no fires and just waste space
    xmin, ymin, xmax, ymax = canada.total_bounds
    top = pts.geometry.y.max() + 150_000
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, top)
    ax.set_axis_off()

    # province / territory codes so the text can refer to them
    label_at = {  # lon, lat - picked by hand to avoid the densest clusters
        "BC": (-125.5, 54.5), "AB": (-114.0, 51.5), "SK": (-106.0, 52.3), "MB": (-98.5, 51.5),
        "ON": (-86.0, 47.5), "QC": (-72.0, 48.5), "NL": (-62.0, 54.5), "NB": (-66.4, 46.4),
        "NS": (-63.3, 45.0), "YT": (-135.5, 64.0), "NT": (-118.0, 64.5), "NU": (-95.0, 64.5),
    }
    lbl = gpd.GeoSeries(gpd.points_from_xy([v[0] for v in label_at.values()],
                                           [v[1] for v in label_at.values()]),
                        crs="EPSG:4326").to_crs(epsg=3978)
    for code, p in zip(label_at, lbl):
        ax.text(p.x, p.y, code, fontsize=8, fontweight="bold", color="#3a3a38",
                ha="center", va="center",
                bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1))

    cause_handles = [Line2D([], [], marker="o", ls="", color=CAUSE_COLOURS[c], ms=6, label=c)
                     for c in ["Lightning", "Human", "Unknown"]]
    size_handles = [plt.scatter([], [], s=dot_size(v), color="#888888", alpha=0.6, lw=0,
                                label=f"{v:,} ha") for v in (1_000, 50_000, 500_000)]
    leg1 = ax.legend(handles=cause_handles, title="Cause", loc="lower left",
                     fontsize=8, title_fontsize=8.5, bbox_to_anchor=(0.0, 0.02))
    ax.add_artist(leg1)
    ax.legend(handles=size_handles, title="Final size", loc="lower left", fontsize=8,
              title_fontsize=8.5, bbox_to_anchor=(0.16, 0.02), labelspacing=1.4,
              borderpad=0.8)

    fig.tight_layout()
    save(fig, "fig5_big_fires_map")

    # how much of the large-fire area is north of 55 degrees / in each agency
    notes["large-fire area north of 55N (%)"] = (
        big.loc[big["LATITUDE"] >= 55, "SIZE_HA"].sum() / big["SIZE_HA"].sum() * 100)
    by_agency = big.groupby("SRC_AGENCY")["SIZE_HA"].sum().sort_values(ascending=False)
    notes["large-fire area by agency (%)"] = (by_agency / by_agency.sum() * 100).round(1).to_dict()
    hb = big[big["cause"] == "Human"]
    notes["human large-fire area south of 55N (%)"] = (
        hb.loc[hb["LATITUDE"] < 55, "SIZE_HA"].sum() / hb["SIZE_HA"].sum() * 100)


# ---------------------------------------------------------------------------
# Figure 6 - heatmap of area burned by year and start month
# ---------------------------------------------------------------------------

def fig_heatmap(df):
    known = df[df["MONTH"].notna()]
    grid = pd.crosstab(known["MONTH"].astype(int), known["YEAR"],
                       values=known["SIZE_HA"], aggfunc="sum").fillna(0)
    grid = grid.reindex(index=range(1, 13), columns=range(FIRST_YEAR, LAST_YEAR + 1), fill_value=0)

    outside = grid.loc[[1, 2, 3, 10, 11, 12]].to_numpy().sum() / grid.to_numpy().sum()
    notes["area from fires starting Oct-Mar (%)"] = outside * 100
    shown = grid.loc[4:9]

    early_share = grid.loc[:5].sum() / grid.sum() * 100
    notes["median % of area from fires starting by end of May"] = early_share.median()
    notes["2023 % of area from fires starting by end of May"] = early_share[2023]
    notes["2025 % of area from fires starting by end of May"] = early_share[2025]
    notes["median May area (Mha)"] = grid.loc[5].median() / 1e6
    notes["May 2023 area (Mha)"] = grid.loc[5, 2023] / 1e6
    notes["May 2025 area (Mha)"] = grid.loc[5, 2025] / 1e6
    notes["years with largest May area"] = list(grid.loc[5].sort_values(ascending=False).index[:4])
    notes["June / July 2023 area (Mha)"] = (round(float(grid.loc[6, 2023]) / 1e6, 2),
                                            round(float(grid.loc[7, 2023]) / 1e6, 2))
    for yr in (1980, 2016, 2019):
        notes[f"{yr}: % area by end of May, total Mha"] = (
            round(float(early_share[yr]), 1), round(float(grid[yr].sum()) / 1e6, 2))

    # Each column is one year and shows how that year's burned area splits by
    # the month the fires started. We tried raw hectares on a log scale first
    # but the timing got lost, and figure 1 already shows the totals.
    pct = shown / grid.sum() * 100

    fig, ax = plt.subplots(figsize=(7, 3.0))
    im = ax.imshow(pct.to_numpy(), aspect="auto", cmap="Oranges", vmin=0, vmax=70,
                   interpolation="nearest")

    ax.set_yticks(range(len(shown.index)))
    ax.set_yticklabels([MONTH_LABELS[m - 1] for m in shown.index])
    years = list(shown.columns)
    ticks = [i for i, yr in enumerate(years) if yr % 5 == 0]
    ax.set_xticks(ticks)
    ax.set_xticklabels([years[i] for i in ticks])
    ax.set_ylabel("Month the fire started")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)

    for yr, ha in ((2023, "right"), (2025, "left")):
        i = years.index(yr)
        ax.add_patch(Rectangle((i - 0.5, -0.5), 1, len(shown.index), fill=False,
                               edgecolor="black", lw=1.1))
        x = i + 0.5 if ha == "right" else i - 0.5
        ax.text(x, -0.6, str(yr), ha=ha, va="bottom", fontsize=8)

    cb = fig.colorbar(im, ax=ax, pad=0.015, fraction=0.04, extend="max")
    cb.set_label("% of that year's\narea burned")
    fig.tight_layout()
    save(fig, "fig6_month_heatmap")


# ---------------------------------------------------------------------------

def print_notes():
    lines = ["Numbers used in the report", "-" * 60]
    for k, v in notes.items():
        if isinstance(v, float):
            v = f"{v:,.3f}" if abs(v) < 10 else f"{v:,.1f}"
        lines.append(f"{k:55s} {v}")
    print("\n" + "\n".join(lines))
    # also keep a copy next to the figures
    (OUT / "numbers_used_in_report.txt").write_text("\n".join(lines) + "\n")


def main():
    get_data()
    df = load_fires()
    fig_yearly(df)
    fig_agencies(df)
    fig_sizes(df)
    fig_causes(df)
    fig_map(df)
    fig_heatmap(df)
    print_notes()


if __name__ == "__main__":
    main()
