"""
PDF reports for the ATU Project Portfolio Dashboard.

    portfolio_pdf(projects, metrics)  -> bytes
    project_pdf(project, metrics_row) -> bytes

Charts are drawn with matplotlib and placed into an A4 landscape PDF built with fpdf2.
"""
from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Wedge  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from fpdf import FPDF  # noqa: E402
from fpdf.fonts import FontFace  # noqa: E402

from project_parser import (CATEGORY_ORDER, Project, category_table, due_text,  # noqa: E402
                            next_period_text, next_portfolio_period, periods_ending_in_month)

HERE = Path(__file__).parent
ATU_LOGO = HERE / "assets" / "atu_logo.png"
PEACE_LOGO = HERE / "assets" / "peaceplus_logo.jpg"
FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"   # DejaVu ships with matplotlib (has €)

TEAL = "#005B5F"
TEAL_LIGHT = "#7FB3B5"
GREY = "#B0B7BB"
PALE = "#E3ECEC"
AMBER = "#F2A900"
DUE_BG = "#FFF3CD"
RAG_COL = {"Green": "#2E8B57", "Amber": "#F2A900", "Red": "#C8102E"}
STATE_COL = {"Verified": TEAL, "Draft": AMBER, "No claim": GREY, "Remaining": PALE}
CAT_COL = {
    "Staff": TEAL,
    "Overheads": "#4E9A9C",
    "Travel & Subsistence": "#F2A900",
    "Equipment": "#6D4C9F",
    "EE & Service Costs": "#C8102E",
}
# one colour per project on the budget pie (cycles if there are more projects)
PROJECT_COLOURS = [
    "#005B5F", "#C8102E", "#F2A900", "#6D4C9F", "#2E8B57", "#1F77B4", "#D35400", "#8C564B",
    "#E377C2", "#17BECF", "#7F7F7F", "#BCBD22", "#003F88", "#9B2335", "#4E9A9C",
]


def tint(hex_colour: str, amount: float = 0.65) -> str:
    """Mix a colour with white (amount = share of white)."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02X}{g:02X}{b:02X}"


def pie_slices(metrics: pd.DataFrame) -> pd.DataFrame:
    """Two slices per project: spent to date (dark) and budget remaining (light).
    Slice sizes add up to each project's current budget; overspend is capped at the budget."""
    rows = []
    for i, (_, m) in enumerate(metrics.iterrows()):
        base = PROJECT_COLOURS[i % len(PROJECT_COLOURS)]
        budget, spent = float(m["Current budget"]), float(m["Actual to date"])
        pct = 100 * spent / budget if budget else 0.0
        rows.append({"Project": m["Project"], "Part": "Spent", "Value": min(spent, budget), "Colour": base,
                     "Budget": budget, "Spent": spent, "Pct": pct})
        rows.append({"Project": m["Project"], "Part": "Remaining", "Value": max(budget - spent, 0.0),
                     "Colour": tint(base), "Budget": budget, "Spent": spent, "Pct": pct})
    return pd.DataFrame(rows)


def pie_geometry(metrics: pd.DataFrame) -> pd.DataFrame:
    """One row per project. Angles in degrees, clockwise from 12 o'clock.
    R_spent is the radius of the spent area: sqrt(spent / budget), so the shaded AREA is
    proportional to the share spent (capped at the full slice when overspent)."""
    rows, start = [], 0.0
    total = float(metrics["Current budget"].clip(lower=0).sum()) or 1.0
    for i, (_, m) in enumerate(metrics.iterrows()):
        base = PROJECT_COLOURS[i % len(PROJECT_COLOURS)]
        budget, spent = max(float(m["Current budget"]), 0.0), float(m["Actual to date"])
        width = 360 * budget / total
        mid = start + width / 2
        pct = 100 * spent / budget if budget else 0.0
        x = np.sin(np.deg2rad(mid))            # screen position of the label (x>0 = right)
        y = np.cos(np.deg2rad(mid))
        side = "top" if y > 0.92 else "bottom" if y < -0.92 else "right" if x >= 0 else "left"
        rows.append({"Project": m["Project"], "Budget": budget, "Spent": spent, "Pct": pct,
                     "Share": 100 * budget / total, "Start": start, "Width": width, "Theta": mid,
                     "R_spent": min(np.sqrt(max(pct, 0) / 100), 1.0), "Over": spent > budget,
                     "Colour": base, "Light": tint(base, 0.7), "Side": side})
        start += width
    return pd.DataFrame(rows)


def eur(x, dp: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    s = f"€{abs(x):,.{dp}f}"
    return f"-{s}" if x < 0 else s


def _d(x, fmt="%d/%m/%Y") -> str:
    return "" if x is None or pd.isna(x) else pd.Timestamp(x).strftime(fmt)


# ---------------------------------------------------------------------------
# Charts (matplotlib -> PNG bytes)
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#999", "axes.titleweight": "bold", "axes.titlecolor": TEAL, "axes.titlesize": 11,
})


def _png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _euro_axis(ax, axis="y"):
    f = matplotlib.ticker.FuncFormatter(
        lambda v, _: f"€{v / 1e6:.1f}M" if abs(v) >= 1e6 else f"€{v / 1e3:.0f}k" if abs(v) >= 1e3 else f"€{v:.0f}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


def pie_png(metrics: pd.DataFrame) -> io.BytesIO:
    g = pie_geometry(metrics)
    fig, ax = plt.subplots(figsize=(10, 6.2))
    for r in g.itertuples():
        t1, t2 = 90 - (r.Start + r.Width), 90 - r.Start     # matplotlib: counter-clockwise from 3 o'clock
        ax.add_patch(Wedge((0, 0), 1, t1, t2, facecolor=r.Light, edgecolor="white", lw=1.5))
        ax.add_patch(Wedge((0, 0), r.R_spent, t1, t2, facecolor=r.Colour, hatch="//",
                           edgecolor=tint(r.Colour, 0.35), lw=0))
        ang = np.deg2rad(90 - r.Theta)
        ha = {"right": "left", "left": "right"}.get(r.Side, "center")
        va = {"top": "bottom", "bottom": "top"}.get(r.Side, "center")
        ax.plot([0.97 * np.cos(ang), 1.06 * np.cos(ang)], [0.97 * np.sin(ang), 1.06 * np.sin(ang)],
                color="#888", lw=0.8)
        ax.text(1.09 * np.cos(ang), 1.09 * np.sin(ang),
                f"{r.Project}\nBudget {eur(r.Budget)}\nSpent {eur(r.Spent)} ({r.Pct:.0f}%)",
                ha=ha, va=va, fontsize=8.5, linespacing=1.3)
    for r in g.itertuples():                              # slice borders drawn on top of the hatching
        t1, t2 = 90 - (r.Start + r.Width), 90 - r.Start
        ax.add_patch(Wedge((0, 0), 1, t1, t2, fill=False, lw=2 if r.Over else 1.5,
                           edgecolor=RAG_COL["Red"] if r.Over else "white"))
    ax.set_xlim(-1.75, 1.75)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Portfolio budget by project · hatched area from the centre = share of budget spent to date")
    return _png(fig)


def budget_actual_png(metrics: pd.DataFrame) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = range(len(metrics))
    w = 0.27
    ax.bar([i - w for i in x], metrics["Current budget"], w, label="Current budget", color=PALE, edgecolor=TEAL)
    ax.bar(list(x), metrics["Budget to date"], w, label="Budget to date", color=TEAL_LIGHT)
    ax.bar([i + w for i in x], metrics["Actual to date"], w, label="Actual to date", color=TEAL)
    ax.scatter(list(x), metrics["Forecast at completion"], marker="D", s=40, color=AMBER, edgecolor="#333",
               zorder=3, label="Forecast at completion")
    ax.set_xticks(list(x), metrics["Project"], rotation=30, ha="right")
    _euro_axis(ax)
    ax.set_title("Budget vs actuals by project")
    ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, -0.28), frameon=False)
    return _png(fig)


def time_vs_budget_png(metrics: pd.DataFrame) -> io.BytesIO:
    n = len(metrics)
    fig, ax = plt.subplots(figsize=(10, max(2.4, 0.42 * n + 1)))
    y = range(n)
    h = 0.38
    ax.barh([i - h / 2 for i in y], metrics["% time"], h, color=TEAL_LIGHT, label="% time elapsed")
    ax.barh([i + h / 2 for i in y], metrics["% budget"], h, color=[RAG_COL[r] for r in metrics["RAG"]],
            label="% budget spent (colour = RAG)")
    for i, (t, b) in enumerate(zip(metrics["% time"], metrics["% budget"])):
        ax.text(t + 1, i - h / 2, f"{t:.0f}%", va="center", fontsize=7.5)
        ax.text(b + 1, i + h / 2, f"{b:.0f}%", va="center", fontsize=7.5)
    ax.set_yticks(list(y), metrics["Project"])
    ax.invert_yaxis()
    ax.set_xlim(0, max(105, metrics[["% time", "% budget"]].max().max() + 10))
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter())
    ax.set_title("Time elapsed vs budget spent")
    ax.legend(ncol=2, loc="upper left", bbox_to_anchor=(0, -0.08), frameon=False)
    return _png(fig)


def timeline_png(plist: list[Project], today: date) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(10, max(1.6, 0.45 * len(plist) + 1)))
    m0 = pd.Timestamp(today.year, today.month, 1)
    ax.axvspan(m0, m0 + pd.offsets.MonthBegin(1), color=AMBER, alpha=0.3, lw=0, zorder=3.5)
    for i, p in enumerate(plist):
        for _, r in p.periods.iterrows():
            if pd.isna(r["start"]) or pd.isna(r["finish"]):
                continue
            s = pd.Timestamp(r["start"])
            e = pd.Timestamp(r["finish"]) + pd.Timedelta(days=1)
            ax.barh(i, e - s, left=s, height=0.6, color=STATE_COL[r["state"]], edgecolor="white", zorder=2)
            ax.text(s + (e - s) / 2, i, r["period"], ha="center", va="center", fontsize=6.5, zorder=3,
                    color="#333" if r["state"] in ("Remaining", "No claim") else "white")
    ax.axvline(pd.Timestamp(today), color=RAG_COL["Red"], ls=":", lw=1.5, zorder=4)
    ax.set_yticks(range(len(plist)), [p.name for p in plist])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    handles = [matplotlib.patches.Patch(color=c, label=k) for k, c in STATE_COL.items()]
    handles.append(matplotlib.patches.Patch(color=AMBER, alpha=0.3, label="This month"))
    ax.legend(handles=handles, ncol=5, loc="upper left", bbox_to_anchor=(0, -0.12), frameon=False)
    ax.set_title("Timeline – completed and remaining periods (red dotted line = today)")
    return _png(fig)


def category_png(t: pd.DataFrame) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(10, 3.1))
    x = range(len(t))
    w = 0.27
    ax.bar([i - w for i in x], t["Current budget"], w, label="Current budget", color=PALE, edgecolor=TEAL)
    ax.bar(list(x), t["Budget to date"], w, label="Budget to date", color=TEAL_LIGHT)
    ax.bar([i + w for i in x], t["Actual to date"], w, label="Actual to date", color=TEAL)
    ax.scatter(list(x), t["Forecast at completion"], marker="D", s=40, color=AMBER, edgecolor="#333", zorder=3,
               label="Forecast at completion")
    ax.set_xticks(list(x), t["Category"])
    _euro_axis(ax)
    ax.set_title("Budget vs actuals by cost category")
    ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, -0.1), frameon=False)
    return _png(fig)


def period_png(p: Project) -> io.BytesIO:
    order = p.periods["period"].tolist()
    L = p.lines
    last_no = int(p.periods.loc[p.periods["completed"], "period_no"].max()) if p.periods["completed"].any() else 0
    fig, ax = plt.subplots(figsize=(10, 3.2))
    if last_no:
        ax.axvspan(-0.5, last_no - 0.5, color=PALE, alpha=0.6, zorder=0)
    bottom = pd.Series(0.0, index=order)
    for c in CATEGORY_ORDER:
        d = L[L["category"] == c].set_index("period").reindex(order).fillna(0)
        if d[["actual", "forecast"]].abs().sum().sum() == 0:
            continue
        ax.bar(order, d["actual"], bottom=bottom, color=CAT_COL[c], label=c, zorder=2)
        bottom += d["actual"]
        ax.bar(order, d["forecast"], bottom=bottom, color=CAT_COL[c], alpha=0.4, hatch="//", zorder=2)
        bottom += d["forecast"]
    bud = L.groupby("period")["budget"].sum().reindex(order).fillna(0)
    ax.scatter(order, bud, marker="_", s=500, linewidths=2.5, color="#222", zorder=3, label="Period budget")
    _euro_axis(ax)
    ax.set_title("Actual / forecast by period vs budget (hatched = forecast, shaded = completed periods)")
    ax.legend(ncol=6, loc="upper left", bbox_to_anchor=(0, -0.1), frameon=False, fontsize=8)
    return _png(fig)


def scurve_png(p: Project) -> io.BytesIO:
    order = p.periods["period"].tolist()
    last_no = int(p.periods.loc[p.periods["completed"], "period_no"].max()) if p.periods["completed"].any() else 0
    per = p.lines.groupby("period")[["budget", "actual", "forecast"]].sum().reindex(order).fillna(0)
    cum = per.cumsum()
    fc = cum["actual"] + cum["forecast"]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.plot(order, cum["budget"], color=GREY, lw=2.5, label="Cumulative budget")
    if last_no:
        ax.plot(order[:last_no], cum["actual"].iloc[:last_no], color=TEAL, lw=2.5, label="Cumulative actual")
    k = max(last_no - 1, 0)
    ax.plot(order[k:], fc.iloc[k:], color=TEAL, lw=2.5, ls="--", label="Cumulative forecast")
    _euro_axis(ax)
    ax.set_title("Cumulative spend profile (S-curve)")
    ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, -0.1), frameon=False)
    return _png(fig)


# ---------------------------------------------------------------------------
# PDF building blocks
# ---------------------------------------------------------------------------
class Report(FPDF):
    def __init__(self, subtitle: str):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.subtitle = subtitle
        self.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
        self.set_auto_page_break(True, margin=14)
        self.set_margins(12, 12, 12)

    def header(self):
        if ATU_LOGO.exists():
            self.image(str(ATU_LOGO), x=12, y=8, h=14)
        if PEACE_LOGO.exists():
            self.image(str(PEACE_LOGO), x=self.w - 12 - 50, y=8, w=50)
        self.set_xy(40, 9)
        self.set_font("DejaVu", "B", 16)
        self.set_text_color(TEAL)
        self.cell(self.w - 104, 8, "Project Portfolio Dashboard", align="C")
        self.set_xy(40, 17)
        self.set_font("DejaVu", "", 9)
        self.set_text_color("#5b6b6e")
        self.cell(self.w - 104, 5, self.subtitle, align="C")
        self.set_y(30)
        self.set_text_color(0)

    def footer(self):
        self.set_y(-10)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color("#888")
        self.cell(0, 5, f"Generated {date.today():%d %b %Y} · all figures in EUR", align="L")
        self.cell(0, 5, f"Page {self.page_no()} / {{nb}}", align="R")

    # -- content helpers ----------------------------------------------------
    def h2(self, text: str, keep: float = 30):
        """Section heading; starts a new page unless `keep` mm fit below it."""
        if self.get_y() + 8 + keep > self.h - 14:
            self.add_page()
        self.set_font("DejaVu", "B", 12)
        self.set_text_color(TEAL)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0)

    def para(self, text: str, size=9, colour="#333"):
        self.set_font("DejaVu", "", size)
        self.set_text_color(colour)
        self.multi_cell(0, 4.8, text, new_x="LMARGIN", new_y="NEXT", markdown=True)
        self.set_text_color(0)
        self.ln(1)

    def callout(self, text: str, fill=DUE_BG, border=AMBER):
        self.set_fill_color(fill)
        self.set_draw_color(border)
        self.set_font("DejaVu", "", 9.5)
        self.multi_cell(0, 6, text, border=1, fill=True, padding=2, new_x="LMARGIN", new_y="NEXT", markdown=True)
        self.ln(3)

    def kpis(self, items: list[tuple[str, str, str]]):
        """Row of KPI boxes: (label, value, sub-caption)."""
        n = len(items)
        gap = 3
        w = (self.w - self.l_margin - self.r_margin - gap * (n - 1)) / n
        y0 = self.get_y()
        for i, (lab, val, sub) in enumerate(items):
            x = self.l_margin + i * (w + gap)
            self.set_fill_color(PALE)
            self.rect(x, y0, w, 19, style="F")
            self.set_xy(x + 2, y0 + 1.5)
            self.set_font("DejaVu", "", 7.5)
            self.set_text_color("#5b6b6e")
            self.cell(w - 4, 4, lab)
            self.set_xy(x + 2, y0 + 6)
            self.set_font("DejaVu", "B", 12)
            self.set_text_color(TEAL)
            self.cell(w - 4, 6, val)
            if sub:
                self.set_xy(x + 2, y0 + 13)
                self.set_font("DejaVu", "", 7)
                self.set_text_color("#5b6b6e")
                self.cell(w - 4, 4, sub)
        self.set_text_color(0)
        self.set_y(y0 + 23)

    def table(self, df: pd.DataFrame, widths: list[float] | None = None, highlight: list[bool] | None = None,
              font_size=7.5, bold_last=False):
        self.set_font("DejaVu", "", font_size)
        self.set_draw_color("#cfd8d8")
        head = FontFace(emphasis="BOLD", color="#FFFFFF", fill_color=TEAL)
        cols = list(df.columns)
        numeric = re.compile(r"^(-?€|[+-]?\d|—$|$)")
        aligns = ["RIGHT" if len(df) and df[c].astype(str).str.match(numeric).all() else "LEFT" for c in cols]
        with super().table(col_widths=widths, headings_style=head, line_height=4.6, text_align=aligns,
                           first_row_as_headings=True, width=self.w - self.l_margin - self.r_margin) as t:
            t.row(cols)
            for i, (_, r) in enumerate(df.iterrows()):
                style = FontFace(fill_color="#FFFFFF")
                if highlight is not None and highlight[i]:
                    style = FontFace(fill_color=DUE_BG)
                if bold_last and i == len(df) - 1:
                    style = FontFace(emphasis="BOLD", fill_color=PALE)
                t.row([str(v) for v in r.values], style=style)
        self.ln(3)

    @staticmethod
    def chart_h(png: io.BytesIO, w: float) -> float:
        from PIL import Image  # installed with matplotlib
        png.seek(0)
        with Image.open(png) as im:
            h = w * im.height / im.width
        png.seek(0)
        return h

    def chart(self, png: io.BytesIO, w: float | None = None):
        w = w or (self.w - self.l_margin - self.r_margin)
        h = self.chart_h(png, w)
        if self.get_y() + h > self.h - 14:
            self.add_page()
        self.image(png, x=self.l_margin + (self.w - self.l_margin - self.r_margin - w) / 2, w=w)
        self.ln(3)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def portfolio_pdf(projects: list[Project], metrics: pd.DataFrame, today: date | None = None) -> bytes:
    today = today or date.today()
    pdf = Report(f"ATU partner budgets · {len(projects)} projects · portfolio report · {today:%d %b %Y}")
    pdf.add_page()

    tot_b = metrics["Current budget"].sum()
    tot_a = metrics["Actual to date"].sum()
    tot_fac = metrics["Forecast at completion"].sum()
    pdf.kpis([
        ("Projects", str(len(metrics)), ""),
        ("Current budget", eur(tot_b), ""),
        ("Budget to date", eur(metrics["Budget to date"].sum()), ""),
        ("Actual to date", eur(tot_a), f"{100 * tot_a / tot_b:.1f}% of budget" if tot_b else ""),
        ("Forecast remaining", eur(metrics["Forecast remaining"].sum()), ""),
        ("Forecast at completion", eur(tot_fac), f"Variance vs budget: {eur(tot_b - tot_fac)}"),
    ])
    counts = metrics["RAG"].value_counts()
    pdf.para("**Traffic lights:** " + " · ".join(f"{r}: {counts.get(r, 0)}" for r in ("Green", "Amber", "Red")))

    due = {p.name: due_text(p, today) for p in projects}
    due_now = {k: v for k, v in due.items() if v}
    if due_now:
        pdf.callout(f"**Reporting periods ending in {today:%B %Y}:** "
                    + "; ".join(f"{k} ({v})" for k, v in due_now.items()))
    else:
        nxt = next_portfolio_period(projects, today)
        pdf.callout(f"**Next reporting period ends {nxt}**" if nxt else "All reporting periods have finished.",
                    fill=PALE, border=TEAL)

    pdf.h2("Projects")
    t = pd.DataFrame({
        "Project": metrics["Project"],
        "Code": metrics["Code"],
        "RAG": metrics["RAG"],
        "Status": metrics["Status"],
        "Due this month": metrics["Project"].map(due),
        "% time": metrics["% time"].map("{:.0f}%".format),
        "% budget": metrics["% budget"].map("{:.0f}%".format),
        "Gap": metrics["Gap (pts)"].map("{:+.1f}".format),
        "Current budget": metrics["Current budget"].map(eur),
        "Budget to date": metrics["Budget to date"].map(eur),
        "Actual to date": metrics["Actual to date"].map(eur),
        "Forecast at compl.": metrics["Forecast at completion"].map(eur),
        "Var. at compl.": metrics["Variance at completion"].map(eur),
    })
    pdf.table(t, widths=[26, 16, 13, 24, 25, 13, 15, 12, 23, 23, 23, 23, 21],
              highlight=[bool(v) for v in t["Due this month"]])
    pdf.para("Highlighted rows have a reporting period ending this month.", size=7.5, colour="#5b6b6e")

    for title, png, w in (("Portfolio budget split by project", pie_png(metrics), 230),
                          ("Budget vs actuals by project", budget_actual_png(metrics), 230),
                          ("Time elapsed vs budget spent", time_vs_budget_png(metrics), 230),
                          ("Timeline", timeline_png(projects, today), 250)):
        pdf.h2(title, keep=pdf.chart_h(png, w))
        pdf.chart(png, w=w)
    return bytes(pdf.output())


def project_pdf(p: Project, m: pd.Series, today: date | None = None) -> bytes:
    today = today or date.today()
    pdf = Report(f"Project report · {p.label} · {today:%d %b %Y}")
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(TEAL)
    pdf.cell(0, 8, f"{p.name}  ", new_x="END")
    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color("#5b6b6e")
    pdf.cell(0, 8, p.code, new_x="LMARGIN", new_y="NEXT")
    pdf.para(f"**Status:** {m['Status']}  ·  **RAG:** {m['RAG']} (gap {m['Gap (pts)']:+.1f} pts)  ·  "
             f"**Lead partner:** {m['Lead partner']}  ·  {_d(m['Start'], '%d %b %Y')} – {_d(m['End'], '%d %b %Y')}"
             f"  ·  {m['Completed periods']} periods completed, {m['Remaining periods']} remaining")

    due = due_text(p, today)
    if due:
        pdf.callout(f"**Reporting period ending this month ({today:%B %Y}):** {due}")
    else:
        pdf.callout(f"**Next reporting period:** {next_period_text(p, today)}", fill=PALE, border=TEAL)

    vtd = m["Variance to date"]
    pdf.kpis([
        ("Current budget", eur(m["Current budget"]), ""),
        ("Budget to date", eur(m["Budget to date"]), f"to end of {m['Last completed']}"),
        ("Actual to date", eur(m["Actual to date"]), f"{eur(abs(vtd))} {'under' if vtd >= 0 else 'over'} budget"),
        ("% time elapsed", f"{m['% time']:.1f}%", f"{m['Completed periods']} of {m['Total periods']} periods"),
        ("% budget spent", f"{m['% budget']:.1f}%", f"{m['Gap (pts)']:+.1f} pts vs time"),
        ("Forecast at completion", eur(m["Forecast at completion"]), f"Variance: {eur(m['Variance at completion'])}"),
    ])

    pdf.h2("Budget vs actuals by cost category")
    t = category_table(p)
    cat_png = category_png(t)
    tot = t.sum(numeric_only=True)
    tot["% spent"] = 100 * tot["Actual to date"] / tot["Current budget"] if tot["Current budget"] else None
    t = pd.concat([t, pd.DataFrame([{"Category": "Total", **tot.to_dict()}])], ignore_index=True)
    show = t.copy()
    for c in show.columns[1:]:
        show[c] = show[c].map((lambda v: "—" if pd.isna(v) else f"{v:.1f}%") if c == "% spent" else eur)
    pdf.table(show, widths=[40] + [29.6] * 8, bold_last=True)
    pdf.para(f"'To date' = up to and including {m['Last completed']}. Variance = budget − actual "
             "(positive = underspent).", size=7.5, colour="#5b6b6e")
    pdf.chart(cat_png, w=200)

    for title, png, w in (("Actual / forecast by period", period_png(p), 205),
                          ("Cumulative spend", scurve_png(p), 215)):
        pdf.h2(title, keep=pdf.chart_h(png, w))
        pdf.chart(png, w=w)

    per_tot = p.lines.groupby("period")[["budget", "value"]].sum()
    tl = p.periods.merge(per_tot, left_on="period", right_index=True, how="left")
    due_set = set(periods_ending_in_month(p, today)["period"])
    ptab = pd.DataFrame({
        "Period": tl["period"],
        "Start": tl["start"].map(_d),
        "Finish": tl["finish"].map(_d),
        "Status": tl["status"],
        "State": tl["state"],
        "Figures": tl["kind"],
        "Budget": tl["budget"].map(eur),
        "Actual / forecast": tl["value"].map(eur),
        "Variance": (tl["budget"] - tl["value"]).map(eur),
    })
    pdf.h2("Reporting periods", keep=4.6 * (len(ptab) + 2))
    pdf.table(ptab, widths=[18, 28, 28, 30, 28, 24, 38, 38, 41], highlight=[x in due_set for x in ptab["Period"]])
    if due_set:
        pdf.para("Highlighted = period ends this month.", size=7.5, colour="#5b6b6e")
    tl_png = timeline_png([p], today)
    pdf.h2("Timeline", keep=pdf.chart_h(tl_png, 250))
    pdf.chart(tl_png, w=250)

    pdf.h2("Travel & overheads: claimed vs actually spent", keep=4.6 * (len(p.spend_check) + 3))
    sc = p.spend_check
    if sc.empty:
        pdf.para("No actual periods yet.")
    else:
        chk = pd.DataFrame({
            "Period": sc["period"],
            "Travel claimed": sc["travel_claimed"].map(lambda v: eur(v, 2)),
            "Travel spent": sc["travel_spend"].map(lambda v: eur(v, 2)),
            "Travel claimed − spent": (sc["travel_claimed"] - sc["travel_spend"]).map(lambda v: eur(v, 2)),
            "Overheads claimed": sc["overhead_claimed"].map(lambda v: eur(v, 2)),
            "Overheads spent": sc["overhead_spend"].map(lambda v: eur(v, 2)),
            "Overheads claimed − spent": (sc["overhead_claimed"] - sc["overhead_spend"]).map(lambda v: eur(v, 2)),
        })
        pdf.table(chk)
        pdf.para("— = actual spend not recorded yet on the last tab.", size=7.5, colour="#5b6b6e")

    if p.warnings:
        pdf.h2("Data checks")
        for w in p.warnings:
            pdf.para(f"• {w}", size=8)
    return bytes(pdf.output())
