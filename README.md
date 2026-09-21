# ATU Project Portfolio Dashboard

A Streamlit dashboard showing the ATU partner budget for every project: portfolio overview plus drill-down per project.

## First-time setup (Windows, Python 3.14)

1. Clone the repo from GitHub and open the folder.
2. Double-click **`run_dashboard.bat`**. On first run it creates a virtual environment and installs the packages; after that it checks for any newly added packages, then starts the app.
3. The dashboard opens in your browser at http://localhost:8501.

Manual alternative:

```
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Loading project files

Either:
- save the downloaded workbooks into the **`data`** folder (they load automatically every time), or
- drag them into the upload box in the sidebar.

Uploaded files replace folder files with the same name. **Workbooks are excluded from Git** (see `.gitignore`), so budgets and staff names never go to GitHub.

## What the files must contain

| Tab | What is read |
|---|---|
| Budget and forecast | Project code (e.g. `P250066`), cost categories, P1…Pn budget + actual/forecast pairs. A column labelled *Actual*, *Actual Spend* or *Claim Approved* = actual; *Forecast* = forecast. Infrastructure is ignored; dashes = 0. |
| Reporting periods | Period, Start, Finish, Status. *Verified* / *Draft* mark reported periods; the last one of these is the "last completed period". |
| Staff salaries and allocation | Staff member name and Project Allocation only (salaries are not shown). |
| Actual travel and overhead cost | *Actuals* columns for travel (col B) and overheads (col D) = money actually spent. Blank = not recorded yet. |

**Project name** comes from the file name (text before `_summary`), e.g. `Prism_summary_report.xlsx` → *Prism*.

**Lead partner** (optional): put a cell anywhere in the workbook reading `Lead Partner:` with the organisation either after the colon or in the cell to the right. The dashboard picks it up automatically.

## How the key measures are calculated

- **% time elapsed** = days from P1 start to the end of the last Verified/Draft period ÷ total project days (P1 start to last period finish).
- **% budget spent** = actuals up to the last completed period ÷ current budget.
- **Gap** = % budget − % time. Traffic light: Green ≤ 10 pts, Amber ≤ 20 pts, Red > 20 pts (adjustable in the sidebar; underspend can be switched on/off).
- **Budget to date** = sum of period budgets up to the last completed period.
- **Forecast at completion** = all actuals + all forecasts.
- **Travel check** = travel actuals on the budget sheet (claimed) vs travel actuals on the last tab (spent). The same is done for overheads (shown on each project page and in the Excel export).
- **Portfolio budget pie** = each slice is a project's share of the total current budget (light colour). The darker, hatched area from the centre of the slice is the share of that project's budget actually spent to date; its area is proportional to % spent. Each slice is labelled with the project's budget and actual spend. Overspent projects get a red outline.
- **Due this month** = any reporting period whose *Finish* date falls in the current calendar month. These projects are listed in a banner and highlighted in the Projects table, and the current month is shaded on the timeline. When nothing ends this month, the banner shows the next reporting period end instead (portfolio: the earliest upcoming one across all projects; project page: that project's next one).

## PDF reports

- **Portfolio page → Download portfolio report (PDF):** headline figures, projects due this month, the projects table, budget pie, budget vs actuals, time vs budget and timeline.
- **Project detail page → Download project report (PDF):** headline figures, cost-category table and chart, period charts (by period and S-curve), reporting periods, timeline, and the travel and overheads check. Staff names are not included.

Reports are A4 landscape with the ATU and PEACEPLUS logos and are built when you click the button.

The *Data checks* panel lists anything odd in a file (invalid dates, category totals not matching period phasing, actuals not aligned with reporting status, forecasts in periods with no budget).

## Files

```
app.py              the dashboard
project_parser.py   reads one workbook, calculates the measures
reports.py          builds the PDF reports
assets/             ATU and PEACEPLUS logos
.streamlit/         theme (ATU teal)
data/               put workbooks here (not committed)
run_dashboard.bat   one-click start on Windows
```
