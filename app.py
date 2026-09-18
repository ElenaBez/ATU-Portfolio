"""
ATU Project Portfolio Dashboard
Run with:  streamlit run app.py
"""
from __future__ import annotations

import base64
import inspect
import io
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from project_parser import CATEGORY_ORDER, Project, category_table, parse_project, project_metrics

HERE = Path(__file__).parent
ATU_LOGO = HERE / "assets" / "atu_logo.png"
PEACE_LOGO = HERE / "assets" / "peaceplus_logo.jpg"

# ---- palette ---------------------------------------------------------------
TEAL = "#005B5F"
TEAL_LIGHT = "#7FB3B5"
GREY = "#B0B7BB"
PALE = "#E3ECEC"
RAG_COL = {"Green": "#2E8B57", "Amber": "#F2A900", "Red": "#C8102E"}
RAG_ICON = {"Green": "🟢", "Amber": "🟡", "Red": "🔴"}
STATE_COL = {"Verified": TEAL, "Draft": "#F2A900", "No claim": GREY, "Remaining": PALE}
CAT_COL = {
    "Staff": TEAL,
    "Overheads": "#4E9A9C",
    "Travel & Subsistence": "#F2A900",
    "Equipment": "#6D4C9F",
    "EE & Service Costs": "#C8102E",
}

st.set_page_config(
    page_title="ATU Project Portfolio",
    page_icon=str(ATU_LOGO) if ATU_LOGO.exists() else "📊",
    layout="wide",
)

st.markdown(
    f"""
    <style>
      .block-container {{padding-top: 3rem;}}
      .atu-brand {{text-align:center; line-height:1.1;}}
      .atu-brand .atu-text {{font-weight:700; font-size:1.25rem; color:{TEAL}; margin-top:.25rem; letter-spacing:.08em;}}
      .dash-title {{text-align:center; color:{TEAL}; margin:0;}}
      .dash-sub {{text-align:center; color:#5b6b6e; margin-top:.2rem;}}
      .badge {{display:inline-block; padding:.2rem .65rem; border-radius:1rem; font-weight:600;
               font-size:.9rem; color:white; margin-right:.4rem;}}
      div[data-testid="stMetricValue"] {{font-size:1.45rem;}}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def eur(x: float, dp: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    s = f"€{abs(x):,.{dp}f}"
    return f"-{s}" if x < 0 else s


def img_b64(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def kpi(col, label: str, value: str, sub: str | None = None):
    col.metric(label, value)
    if sub:
        col.caption(sub)


def badge(text: str, colour: str) -> str:
    return f'<span class="badge" style="background:{colour}">{text}</span>'


def status_colour(status: str) -> str:
    s = status.lower()
    return STATE_COL["Verified"] if "verified" in s else STATE_COL["Draft"] if "draft" in s else GREY


DF_PARAMS = inspect.signature(st.dataframe).parameters
EURO = st.column_config.NumberColumn(format="euro")
PCT = st.column_config.NumberColumn(format="%.1f%%")


def pct_bar(label):
    return st.column_config.ProgressColumn(label, format="%.0f%%", min_value=0, max_value=100)


@st.cache_data(show_spinner=False)
def load(data: bytes, filename: str) -> Project:
    return parse_project(data, filename)


def fig_layout(fig: go.Figure, height=380, **kw) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        plot_bgcolor="white",
        **kw,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#eef2f2")
    return fig


# ---------------------------------------------------------------------------
# Sidebar: data & settings
# ---------------------------------------------------------------------------
st.sidebar.header("Project files")
uploads = st.sidebar.file_uploader(
    "Drag in the project summary workbooks (.xlsx)",
    type=["xlsx", "xlsm"],
    accept_multiple_files=True,
)
folder = st.sidebar.text_input(
    "…or read every .xlsx in a folder",
    value=str(HERE / "data"),
    help="Handy for monthly updates: save all 15 downloads into this folder and they load automatically.",
)

files: dict[str, bytes] = {}
fp = Path(folder).expanduser()
if folder and fp.is_dir():
    for f in sorted(fp.glob("*.xls[xm]")):
        if not f.name.startswith("~$"):
            files[f.name] = f.read_bytes()
for u in uploads or []:
    files[u.name] = u.getvalue()          # uploads override same-named folder files

st.sidebar.header("Traffic lights")
st.sidebar.caption("Gap = % budget spent − % time elapsed (to last completed period).")
amber = st.sidebar.number_input("Amber when gap exceeds (pts)", 0.0, 100.0, 10.0, 1.0)
red = st.sidebar.number_input("Red when gap exceeds (pts)", 0.0, 100.0, 20.0, 1.0)
flag_under = st.sidebar.toggle("Flag underspend as well as overspend", value=True)

projects: list[Project] = []
load_errors: list[str] = []
for name, data in files.items():
    try:
        projects.append(load(data, name))
    except Exception as e:  # noqa: BLE001
        load_errors.append(f"**{name}** – {e}")

projects.sort(key=lambda p: p.name.lower())
by_label = {p.label: p for p in projects}

st.sidebar.header("View")
if "view" not in st.session_state:
    st.session_state.view = "Portfolio"
st.sidebar.radio("Page", ["Portfolio", "Project detail"], key="view", label_visibility="collapsed")


def open_project(label: str):
    st.session_state.project = label
    st.session_state.view = "Project detail"


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
def header(subtitle: str, big: bool = True):
    c1, c2, c3 = st.columns([1.2, 5, 2.2], vertical_alignment="center")
    with c1:
        if ATU_LOGO.exists():
            st.markdown(
                f'<div class="atu-brand"><img src="{img_b64(ATU_LOGO)}" width="{70 if big else 48}">'
                f'<div class="atu-text">ATU</div></div>',
                unsafe_allow_html=True,
            )
    with c2:
        tag = "h1" if big else "h2"
        st.markdown(f'<{tag} class="dash-title">Project Portfolio Dashboard</{tag}>', unsafe_allow_html=True)
        st.markdown(f'<div class="dash-sub">{subtitle}</div>', unsafe_allow_html=True)
    with c3:
        if PEACE_LOGO.exists():
            st.image(str(PEACE_LOGO), width=230 if big else 170)
    st.divider()


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def timeline_fig(plist: list[Project], height=None) -> go.Figure:
    fig = go.Figure()
    shown = set()
    for p in plist:
        for _, r in p.periods.iterrows():
            if pd.isna(r["start"]) or pd.isna(r["finish"]):
                continue
            s = pd.Timestamp(r["start"])
            e = pd.Timestamp(r["finish"]) + pd.Timedelta(days=1)
            st_ = r["state"]
            fig.add_trace(go.Bar(
                y=[p.label], x=[(e - s).total_seconds() * 1000], base=[s], orientation="h",
                marker=dict(color=STATE_COL[st_], line=dict(color="white", width=1.5)),
                name=st_, legendgroup=st_, showlegend=st_ not in shown,
                text=r["period"], textposition="inside", insidetextanchor="middle",
                textfont=dict(color="#333" if st_ in ("Remaining", "No claim") else "white", size=10),
                hovertemplate=(f"<b>{p.name} {r['period']}</b><br>{r['start']:%d %b %Y} – {r['finish']:%d %b %Y}"
                               f"<br>{r['status'] or st_}<extra></extra>"),
            ))
            shown.add(st_)
    today = pd.Timestamp(date.today())
    fig.add_shape(type="line", x0=today, x1=today, y0=0, y1=1, yref="paper",
                  line=dict(color=RAG_COL["Red"], dash="dot", width=2))
    fig.add_annotation(x=today, y=1.0, yref="paper", text="Today", showarrow=False,
                       font=dict(color=RAG_COL["Red"]), yanchor="bottom")
    fig.update_xaxes(type="date")
    fig.update_yaxes(autorange="reversed")
    return fig_layout(fig, height or max(180, 60 + 42 * len(plist)), barmode="overlay", bargap=0.35)


def time_vs_budget_fig(m: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(y=m["Project"], x=m["% time"], orientation="h", name="% time elapsed",
                marker_color=TEAL_LIGHT, text=m["% time"].map("{:.0f}%".format), textposition="outside")
    fig.add_bar(y=m["Project"], x=m["% budget"], orientation="h", name="% budget spent (colour = RAG)",
                marker_color=[RAG_COL[r] for r in m["RAG"]],
                text=m["% budget"].map("{:.0f}%".format), textposition="outside")
    fig.update_xaxes(range=[0, max(105, m[["% time", "% budget"]].max().max() + 10)], ticksuffix="%")
    fig.update_yaxes(autorange="reversed")
    return fig_layout(fig, max(220, 80 + 55 * len(m)), barmode="group")


def budget_actual_fig(m: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=m["Project"], y=m["Current budget"], name="Current budget", marker_color=PALE,
                marker_line=dict(color=TEAL, width=1))
    fig.add_bar(x=m["Project"], y=m["Budget to date"], name="Budget to date", marker_color=TEAL_LIGHT)
    fig.add_bar(x=m["Project"], y=m["Actual to date"], name="Actual to date", marker_color=TEAL)
    fig.add_scatter(x=m["Project"], y=m["Forecast at completion"], mode="markers", name="Forecast at completion",
                    marker=dict(symbol="diamond", size=12, color=RAG_COL["Amber"], line=dict(color="#333", width=1)))
    fig.update_yaxes(tickprefix="€", tickformat="~s")
    return fig_layout(fig, 400, barmode="group")


def category_fig(t: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=t["Category"], y=t["Current budget"], name="Current budget", marker_color=PALE,
                marker_line=dict(color=TEAL, width=1))
    fig.add_bar(x=t["Category"], y=t["Budget to date"], name="Budget to date", marker_color=TEAL_LIGHT)
    fig.add_bar(x=t["Category"], y=t["Actual to date"], name="Actual to date", marker_color=TEAL)
    fig.add_scatter(x=t["Category"], y=t["Forecast at completion"], mode="markers", name="Forecast at completion",
                    marker=dict(symbol="diamond", size=12, color=RAG_COL["Amber"], line=dict(color="#333", width=1)))
    fig.update_yaxes(tickprefix="€", tickformat="~s")
    return fig_layout(fig, 380, barmode="group")


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
if not projects:
    header("ATU partner budgets · all figures in EUR")
    st.info(
        "Drag the project summary workbooks into the sidebar, or save them into the **data** folder "
        "next to this app and they'll load automatically."
    )
    for e in load_errors:
        st.error(e)
    st.stop()

metrics = pd.DataFrame([project_metrics(p, amber, red, flag_under) for p in projects])
metrics["Label"] = [p.label for p in projects]
metrics["Periods"] = metrics["Completed periods"].astype(str) + " / " + metrics["Total periods"].astype(str)
metrics["RAG "] = metrics["RAG"].map(lambda r: f"{RAG_ICON[r]} {r}")


# ===========================================================================
# PORTFOLIO PAGE
# ===========================================================================
def portfolio_page():
    header(f"ATU partner budgets · {len(projects)} projects · all figures in EUR · generated {date.today():%d %b %Y}")

    tot_b = metrics["Current budget"].sum()
    tot_a = metrics["Actual to date"].sum()
    tot_btd = metrics["Budget to date"].sum()
    tot_fac = metrics["Forecast at completion"].sum()
    k = st.columns(6)
    kpi(k[0], "Projects", str(len(metrics)))
    kpi(k[1], "Current budget", eur(tot_b))
    kpi(k[2], "Budget to date", eur(tot_btd))
    kpi(k[3], "Actual to date", eur(tot_a), f"{100 * tot_a / tot_b:.1f}% of budget" if tot_b else None)
    kpi(k[4], "Forecast remaining", eur(metrics["Forecast remaining"].sum()))
    kpi(k[5], "Forecast at completion", eur(tot_fac), f"Variance vs budget: {eur(tot_b - tot_fac)}")

    counts = metrics["RAG"].value_counts()
    st.markdown(
        " ".join(badge(f"{RAG_ICON[r]} {r}: {counts.get(r, 0)}", RAG_COL[r]) for r in ("Green", "Amber", "Red"))
        + " &nbsp; "
        + " ".join(badge(f"Latest period {s}: {(metrics['Last status'].str.lower() == s.lower()).sum()}",
                         STATE_COL[s]) for s in ("Verified", "Draft")),
        unsafe_allow_html=True,
    )

    st.subheader("Projects")
    st.caption("Select a row, then open the project to drill down.")
    cols = ["RAG ", "Project", "Code", "Lead partner", "Status", "Periods", "% time", "% budget", "Gap (pts)",
            "Current budget", "Budget to date", "Actual to date", "Variance to date",
            "Forecast at completion", "Variance at completion"]
    ev = st.dataframe(
        metrics[cols],
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="portfolio_table",
        column_config={
            "RAG ": st.column_config.TextColumn("RAG"),
            "% time": pct_bar("% time"),
            "% budget": pct_bar("% budget"),
            "Gap (pts)": st.column_config.NumberColumn(format="%+.1f"),
            **{c: EURO for c in cols[9:]},
        },
    )
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        lab = metrics.iloc[rows[0]]["Label"]
        st.button(f"Open {lab} ▶", type="primary", on_click=open_project, args=(lab,))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Budget vs actuals by project")
        st.plotly_chart(budget_actual_fig(metrics), key="pf_bva")
    with c2:
        st.subheader("Time elapsed vs budget spent")
        st.plotly_chart(time_vs_budget_fig(metrics), key="pf_tvb")

    st.subheader("Timeline – completed and remaining periods")
    st.plotly_chart(timeline_fig(projects), key="pf_tl")

    st.subheader("Portfolio by cost category")
    cats = pd.concat([category_table(p) for p in projects])
    cat_tot = cats.groupby("Category", as_index=False).sum(numeric_only=True)
    cat_tot["% spent"] = 100 * cat_tot["Actual to date"] / cat_tot["Current budget"]
    cat_tot["Category"] = pd.Categorical(cat_tot["Category"], CATEGORY_ORDER, ordered=True)
    cat_tot = cat_tot.sort_values("Category")
    cat_tot["Category"] = cat_tot["Category"].astype(str)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(category_fig(cat_tot), key="pf_cat")
    with c2:
        st.dataframe(
            cat_tot[["Category", "Current budget", "Actual to date", "Forecast at completion", "% spent"]],
            hide_index=True,
            column_config={"Current budget": EURO, "Actual to date": EURO, "Forecast at completion": EURO,
                           "% spent": PCT},
        )

    st.subheader("Travel: claimed vs actually spent")
    st.caption("Only periods where actual travel spend has been recorded on the last tab are compared.")
    trows = []
    for p in projects:
        sc = p.spend_check.dropna(subset=["travel_spend"])
        trows.append({"Project": p.name, "Periods compared": len(sc),
                      "Travel claimed": sc["travel_claimed"].sum(), "Travel actually spent": sc["travel_spend"].sum()})
    tdf = pd.DataFrame(trows)
    tdf["Claimed − spent"] = tdf["Travel claimed"] - tdf["Travel actually spent"]
    st.dataframe(tdf, hide_index=True, column_config={c: EURO for c in tdf.columns[2:]})

    with st.expander(f"Data checks ({sum(len(p.warnings) for p in projects) + len(load_errors)})"):
        for e in load_errors:
            st.error(e)
        for p in projects:
            for w in p.warnings:
                st.warning(f"**{p.label}** – {w}")
        if not load_errors and not any(p.warnings for p in projects):
            st.success("No issues found.")

    st.download_button(
        "⬇ Download portfolio summary (Excel)",
        data=export_excel(),
        file_name=f"ATU_portfolio_summary_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def export_excel() -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out = metrics.drop(columns=["Label", "RAG ", "Periods"])
        out.to_excel(xw, sheet_name="Portfolio", index=False)
        pd.concat([category_table(p).assign(Project=p.name, Code=p.code) for p in projects]).to_excel(
            xw, sheet_name="By category", index=False)
        pd.concat([
            p.lines.assign(Project=p.name, Code=p.code)[
                ["Project", "Code", "period", "category", "kind", "budget", "actual", "forecast"]]
            for p in projects
        ]).to_excel(xw, sheet_name="By period", index=False)
        pd.concat([p.spend_check.assign(Project=p.name, Code=p.code) for p in projects]).to_excel(
            xw, sheet_name="Travel & OH check", index=False)
        pd.concat([p.staff.assign(Project=p.name, Code=p.code) for p in projects]).to_excel(
            xw, sheet_name="People", index=False)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = max(12, min(40, len(str(col[0].value)) + 4))
    return buf.getvalue()


# ===========================================================================
# PROJECT PAGE
# ===========================================================================
def project_page():
    labels = list(by_label)
    if st.session_state.get("project") not in labels:
        st.session_state.project = labels[0]
    header("Project drill-down · all figures in EUR", big=False)
    sel = st.selectbox("Project", labels, key="project")
    p = by_label[sel]
    m = metrics.set_index("Label").loc[sel]
    last_no = int(p.periods.loc[p.periods["completed"], "period_no"].max()) if p.periods["completed"].any() else 0

    st.markdown(
        f"### {p.name} &nbsp;<small style='color:#5b6b6e'>{p.code}</small>", unsafe_allow_html=True)
    st.markdown(
        badge(m["Status"], status_colour(m["Status"]))
        + badge(f"{RAG_ICON[m['RAG']]} {m['RAG']} · gap {m['Gap (pts)']:+.1f} pts", RAG_COL[m["RAG"]])
        + f"&nbsp; Lead partner: <b>{m['Lead partner']}</b> &nbsp;·&nbsp; "
        f"{m['Start']:%d %b %Y} – {m['End']:%d %b %Y} &nbsp;·&nbsp; "
        f"<b>{m['Completed periods']}</b> periods completed, <b>{m['Remaining periods']}</b> remaining",
        unsafe_allow_html=True,
    )

    k = st.columns(6)
    kpi(k[0], "Current budget", eur(m["Current budget"]))
    kpi(k[1], "Budget to date", eur(m["Budget to date"]), f"to end of {m['Last completed']}")
    vtd = m["Variance to date"]
    kpi(k[2], "Actual to date", eur(m["Actual to date"]),
        f"{eur(abs(vtd))} {'under' if vtd >= 0 else 'over'} budget to date")
    kpi(k[3], "% time elapsed", f"{m['% time']:.1f}%", f"{m['Completed periods']} of {m['Total periods']} periods")
    kpi(k[4], "% budget spent", f"{m['% budget']:.1f}%", f"{m['Gap (pts)']:+.1f} pts vs time")
    kpi(k[5], "Forecast at completion", eur(m["Forecast at completion"]),
        f"Variance vs budget: {eur(m['Variance at completion'])}")

    tabs = st.tabs(["Budget vs actuals", "By period", "Travel & overheads check", "People", "Timeline"])

    # ---- Budget vs actuals by category ----------------------------------
    with tabs[0]:
        t = category_table(p)
        st.plotly_chart(category_fig(t), key="pj_cat")
        tot = t.sum(numeric_only=True)
        tot["% spent"] = 100 * tot["Actual to date"] / tot["Current budget"] if tot["Current budget"] else None
        t = pd.concat([t, pd.DataFrame([{"Category": "Total", **tot.to_dict()}])], ignore_index=True)
        st.dataframe(
            t, hide_index=True,
            column_config={**{c: EURO for c in t.columns if c not in ("Category", "% spent")},
                           "% spent": pct_bar("% spent")},
        )
        st.caption(f"'To date' = up to and including {m['Last completed']}. Variance = budget − actual "
                   "(positive = underspent).")

    # ---- By period --------------------------------------------------------
    with tabs[1]:
        cats = [c for c in CATEGORY_ORDER if c in p.lines["category"].unique()
                and p.lines.loc[p.lines["category"] == c, ["budget", "value"]].abs().sum().sum() > 0]
        chosen = st.multiselect("Cost categories", cats, default=cats, key=f"cats_{sel}")
        L = p.lines[p.lines["category"].isin(chosen)]
        order = p.periods["period"].tolist()
        per = L.groupby("period").agg(budget=("budget", "sum"), actual=("actual", "sum"),
                                      forecast=("forecast", "sum")).reindex(order).fillna(0)

        fig = go.Figure()
        for c in chosen:
            d = L[L["category"] == c].set_index("period").reindex(order)
            fig.add_bar(x=order, y=d["actual"], name=f"{c} (actual)", marker_color=CAT_COL[c],
                        legendgroup=c)
            fig.add_bar(x=order, y=d["forecast"], name=f"{c} (forecast)", marker_color=CAT_COL[c],
                        marker_pattern_shape="/", opacity=0.45, legendgroup=c, showlegend=False)
        fig.add_scatter(x=order, y=per["budget"], mode="markers", name="Period budget",
                        marker=dict(symbol="line-ew-open", size=34, color="#222", line=dict(color="#222", width=3)))
        if last_no:
            fig.add_vrect(x0=-0.5, x1=last_no - 0.5, fillcolor=PALE, opacity=0.45, line_width=0,
                          annotation_text="completed periods", annotation_position="bottom left")
        fig.update_yaxes(tickprefix="€", tickformat="~s")
        st.markdown("**Actual / forecast by period vs budget** (hatched = forecast)")
        fig = fig_layout(fig, 460, barmode="stack")
        fig.update_layout(margin=dict(t=80))
        st.plotly_chart(fig, key="pj_per")

        cum = per.cumsum()
        fig2 = go.Figure()
        fig2.add_scatter(x=order, y=cum["budget"], name="Cumulative budget", line=dict(color=GREY, width=3))
        act_x = order[:last_no] if last_no else []
        fig2.add_scatter(x=act_x, y=cum["actual"].iloc[:last_no], name="Cumulative actual",
                         line=dict(color=TEAL, width=3))
        fc = (cum["actual"] + cum["forecast"])
        fig2.add_scatter(x=order[max(last_no - 1, 0):], y=fc.iloc[max(last_no - 1, 0):],
                         name="Cumulative forecast", line=dict(color=TEAL, width=3, dash="dash"))
        fig2.update_yaxes(tickprefix="€", tickformat="~s")
        st.markdown("**Cumulative spend profile (S-curve)**")
        st.plotly_chart(fig_layout(fig2, 360), key="pj_cum")

        view = st.radio("Table", ["Actual / forecast", "Budget", "Variance (budget − actual/forecast)"],
                        horizontal=True, key=f"tbl_{sel}")
        val = {"Actual / forecast": "value", "Budget": "budget"}.get(view)
        if val:
            piv = L.pivot_table(index="category", columns="period", values=val, aggfunc="sum")
        else:
            piv = (L.assign(v=L["budget"] - L["value"])
                   .pivot_table(index="category", columns="period", values="v", aggfunc="sum"))
        piv = piv.reindex(columns=order).reindex([c for c in CATEGORY_ORDER if c in piv.index])
        piv.loc["Total"] = piv.sum()
        piv["Total"] = piv.sum(axis=1)
        kinds = dict(zip(p.periods["period"], p.periods["kind"]))
        piv.columns = [f"{c} ({kinds[c][0]})" if c in kinds else c for c in piv.columns]
        st.dataframe(piv.round(2), column_config={c: EURO for c in piv.columns})
        st.caption("(A) = actual, (F) = forecast, taken from the column labels in the budget sheet.")

    # ---- Travel & overheads check ----------------------------------------
    with tabs[2]:
        sc = p.spend_check.copy()
        sc["travel_diff"] = sc["travel_claimed"] - sc["travel_spend"]
        sc["overhead_diff"] = sc["overhead_claimed"] - sc["overhead_spend"]
        st.markdown("Compares what was **claimed** (actuals on the budget sheet) with what was **actually spent** "
                    "(last tab). Blank = spend not yet recorded; those periods are left out of the totals.")
        c1, c2 = st.columns(2)
        for col, kind, lab in ((c1, "travel", "Travel"), (c2, "overhead", "Overheads")):
            with col:
                rec = sc.dropna(subset=[f"{kind}_spend"])
                kpi(st, f"{lab}: claimed − spent ({len(rec)} period{'s' if len(rec) != 1 else ''} recorded)",
                    eur(rec[f"{kind}_diff"].sum(), 2),
                    f"Claimed {eur(rec[f'{kind}_claimed'].sum(), 2)} · spent {eur(rec[f'{kind}_spend'].sum(), 2)}")
                fig = go.Figure()
                fig.add_bar(x=sc["period"], y=sc[f"{kind}_claimed"], name="Claimed", marker_color=TEAL_LIGHT)
                fig.add_bar(x=sc["period"], y=sc[f"{kind}_spend"], name="Actually spent", marker_color=TEAL)
                fig.update_yaxes(tickprefix="€")
                st.markdown(f"**{lab}**")
                st.plotly_chart(fig_layout(fig, 300, barmode="group"), key=f"pj_chk_{kind}")
        show = sc.rename(columns={
            "period": "Period", "travel_claimed": "Travel claimed", "travel_spend": "Travel spent",
            "travel_diff": "Travel claimed − spent", "overhead_claimed": "Overheads claimed",
            "overhead_spend": "Overheads spent", "overhead_diff": "Overheads claimed − spent"})
        show = show[["Period", "Travel claimed", "Travel spent", "Travel claimed − spent",
                     "Overheads claimed", "Overheads spent", "Overheads claimed − spent"]]
        st.dataframe(show, hide_index=True, column_config={c: EURO for c in show.columns[1:]},
                     **({"placeholder": "not recorded"} if "placeholder" in DF_PARAMS else {}))

    # ---- People -----------------------------------------------------------
    with tabs[3]:
        if p.staff.empty:
            st.info("No staff listed in this file.")
        else:
            c1, c2 = st.columns([1, 3])
            c1.metric("People", len(p.staff))
            c1.metric("Total FTE on project", f"{p.staff['Allocation'].sum():.2f}")
            c2.dataframe(
                p.staff.assign(Allocation=p.staff["Allocation"] * 100), hide_index=True,
                column_config={"Allocation": st.column_config.ProgressColumn(
                    "Project allocation", format="%.0f%%", min_value=0, max_value=100)},
            )

    # ---- Timeline ---------------------------------------------------------
    with tabs[4]:
        st.plotly_chart(timeline_fig([p], 170), key="pj_tl")
        per_tot = p.lines.groupby("period")[["budget", "value"]].sum()
        tl = p.periods.merge(per_tot, left_on="period", right_index=True, how="left")
        tl = tl.rename(columns={"period": "Period", "start": "Start", "finish": "Finish", "status": "Status",
                                "state": "State", "kind": "Figures", "budget": "Budget",
                                "value": "Actual / forecast"})
        st.dataframe(tl[["Period", "Start", "Finish", "Status", "State", "Figures", "Budget", "Actual / forecast"]],
                     hide_index=True,
                     column_config={"Budget": EURO, "Actual / forecast": EURO,
                                    "Start": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                    "Finish": st.column_config.DateColumn(format="DD/MM/YYYY")})

    if p.warnings:
        with st.expander(f"Data checks for this project ({len(p.warnings)})"):
            for w in p.warnings:
                st.warning(w)


if st.session_state.view == "Portfolio":
    portfolio_page()
else:
    project_page()
