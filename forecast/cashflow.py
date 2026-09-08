"""The manual cash flow model, read from the workbook as it is.

The workbook has three kinds of sheet and this reads all of them:
  * "Assumptions & Variables": scalars (B2B exempt share, Shopify share,
    repayment rate, loan advance and total to repay).
  * "12-Month Cash Flow & Financial": blocks of monthly Net Sales / Shipping /
    Taxes / Total Sales. The blocks headed "Sales Breakdown" are actual years;
    those headed "Projected Sales" are the scenarios (Algorithm 1, 2, 3).
  * "IN OUT flows (Algorithm N)": the cash mechanics per scenario: the advance,
    gross sales, overheads, cost lines that scale with sales, the Shopify
    Capital repayment, net cash, working capital and the loan balance.

Two things are derived from it. A DayProfile spreads a monthly target over
its days (weekday and intra-month shape learned from the store's own history)
so the target is a daily baseline feature and a daily benchmark. And
project_cash reruns a scenario's cash mechanics on a different sales line,
which is how a forecast becomes a working-capital path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

EXCEL_EPOCH = date(1899, 12, 30)

SALES_LINES = {"net sales": "net_sales", "shipping": "shipping", "taxes": "taxes", "total sales": "total_sales"}
FLOW_LINES = [  # (label prefix, column); order matters, first match wins
    ("shopify advance", "advance"), ("gross sales", "gross_sales"), ("total cash in", "cash_in"),
    ("base monthly", "overheads"), ("glass", "glass"), ("projector", "projector"), ("market", "marketing"),
    ("unexpected", "unexpected"), ("shopify repay", "repayment"), ("total cash out", "cash_out"),
    ("net cash", "net_cash"), ("working cap", "working_capital"),
    ("starting loan", "loan_start"), ("less: repay", "loan_repaid"), ("ending loan", "loan_end"),
]
SCALING_LINES = ("glass", "projector", "marketing", "unexpected")


def excel_date(v) -> Optional[date]:
    """An Excel serial or a datetime cell to a date; anything else is None."""
    if hasattr(v, "date"):
        return v.date() if hasattr(v, "hour") else v
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return EXCEL_EPOCH + timedelta(days=int(n)) if 20000 < n < 80000 else None


def month_start(d) -> pd.Timestamp:
    return pd.Timestamp(d).to_period("M").to_timestamp()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def _padded(rows: List[tuple], width: int = 2) -> List[tuple]:
    """read_only sheets hand back ragged rows, an empty tuple for a blank one."""
    w = max([width] + [len(r) for r in rows])
    return [tuple(r) + (None,) * (w - len(r)) for r in rows]


def _sales_blocks(rows: List[tuple]) -> List[Tuple[str, pd.DataFrame]]:
    """Every 'Month' header row starts a block; the sales lines under it are its body."""
    blocks: List[Tuple[str, pd.DataFrame]] = []
    label_above = ""
    i = 0
    while i < len(rows):
        row = rows[i]
        a = str(row[0] or "").strip()
        b = str(row[1] or "").strip().lower()
        if a and b != "month":
            label_above = a
        if b == "month":
            label = a or label_above
            months, cols = [], []
            for j, v in enumerate(row[2:], start=2):
                d = excel_date(v)
                if d is None:
                    if months:
                        break
                    continue
                months.append(month_start(d)); cols.append(j)
            body: Dict[str, list] = {}
            k = i + 1
            while k < len(rows):
                lab = str(rows[k][1] or "").strip().lower()
                if lab == "month":
                    break
                if lab in SALES_LINES:
                    body[SALES_LINES[lab]] = [float(rows[k][c] or 0) for c in cols]
                elif body and not lab and not str(rows[k][0] or "").strip():
                    # a blank row closes the block once it has content
                    if all(v in (None, "") for v in rows[k]):
                        break
                k += 1
            if months and body:
                df = pd.DataFrame({"month": months, **body})
                blocks.append((label, df))
            i = k
            continue
        i += 1
    return blocks


def _flow_block(rows: List[tuple]) -> pd.DataFrame:
    header = rows[0]
    months, cols = [], []
    for j, v in enumerate(header[1:], start=1):
        d = excel_date(v)
        if d is None:
            if months:
                break
            continue
        months.append(month_start(d)); cols.append(j)
    body: Dict[str, list] = {}
    for row in rows[1:]:
        lab = str(row[0] or "").strip().lower()
        if not lab:
            continue
        for prefix, col in FLOW_LINES:
            if lab.startswith(prefix) and col not in body:
                body[col] = [float(row[c] or 0) if c < len(row) else 0.0 for c in cols]
                break
    return pd.DataFrame({"month": months, **body})


@dataclass
class DayProfile:
    """Multiplicative day weights: a weekday shape and an intra-month shape, each
    with mean 1, learned from the store's own daily total. Spreads a monthly
    figure over its days so a monthly target becomes a daily line."""
    dow: np.ndarray
    dom: np.ndarray

    @classmethod
    def uniform(cls) -> "DayProfile":
        return cls(np.ones(7), np.ones(31))

    @classmethod
    def fit(cls, daily_total: pd.Series, shrink: float = 30.0) -> "DayProfile":
        s = pd.Series(daily_total).astype(float)
        s.index = pd.DatetimeIndex(s.index)
        s = s[s.index >= s.index.max() - pd.Timedelta(days=730)]
        if s.sum() <= 0 or len(s) < 60:
            return cls.uniform()
        mean = s.mean()
        by_dow = s.groupby(s.index.dayofweek).agg(["mean", "count"])
        dow = np.ones(7)
        for d, r in by_dow.iterrows():
            dow[d] = (r["mean"] * r["count"] + mean * shrink) / (mean * (r["count"] + shrink))
        # intra-month: each day's sales relative to its own month's mean
        month_mean = s.groupby(s.index.to_period("M")).transform("mean").replace(0, np.nan)
        rel = (s / month_mean).dropna()
        by_dom = rel.groupby(rel.index.day).agg(["mean", "count"])
        dom = np.ones(31)
        for d, r in by_dom.iterrows():
            dom[d - 1] = (r["mean"] * r["count"] + shrink) / (r["count"] + shrink)
        return cls(dow / dow.mean(), dom / dom.mean())

    def weights(self, dates: pd.DatetimeIndex) -> np.ndarray:
        idx = pd.DatetimeIndex(dates)
        return self.dow[idx.dayofweek] * self.dom[idx.day - 1]


def daily_from_monthly(monthly: pd.DataFrame, profile: DayProfile, columns: Sequence[str] = ("net_sales",)) -> pd.DataFrame:
    """Spread each month's figures over its days by the profile. Sums back to the
    month exactly, which is what makes it a benchmark and not an estimate."""
    parts = []
    for _, row in monthly.iterrows():
        m = pd.Timestamp(row["month"])
        days = pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="D")
        w = profile.weights(days)
        w = w / w.sum()
        part = pd.DataFrame({"date": days})
        for c in columns:
            part[c + "_target"] = float(row[c]) * w
        parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["date"] + [c + "_target" for c in columns])


@dataclass
class CashFlowModel:
    actuals: pd.DataFrame                 # month, net_sales, shipping, taxes, total_sales (two actual years)
    scenarios: Dict[str, pd.DataFrame]    # name -> the same columns for the projection year
    flows: Dict[str, pd.DataFrame]        # name -> month + FLOW_LINES columns
    assumptions: Dict[str, float]

    @classmethod
    def from_workbook(cls, path) -> "CashFlowModel":
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        assumptions: Dict[str, float] = {}
        sales_rows: List[tuple] = []
        flows: Dict[str, pd.DataFrame] = {}
        for ws in wb.worksheets:
            title = ws.title.lower()
            rows = _padded([tuple(r) for r in ws.iter_rows(values_only=True)])
            if title.startswith("assumption"):
                for r in rows:
                    if r and r[0] and len(r) > 1 and isinstance(r[1], (int, float)):
                        assumptions[_slug(str(r[0]))] = float(r[1])
            elif "flow" in title and re.search(r"algorithm\s*\d+", title):
                m = re.search(r"algorithm\s*(\d+)", title)
                flows[f"Algorithm {m.group(1)}"] = _flow_block(rows)
            elif "cash flow" in title:
                sales_rows = rows
        blocks = _sales_blocks(sales_rows)
        actual = [df for label, df in blocks if not label.lower().startswith("projected")]
        projected = [(label, df) for label, df in blocks if label.lower().startswith("projected")]
        actuals = (pd.concat(actual).drop_duplicates("month").sort_values("month").reset_index(drop=True)
                   if actual else pd.DataFrame(columns=["month"] + list(SALES_LINES.values())))
        scenarios: Dict[str, pd.DataFrame] = {}
        for i, (label, df) in enumerate(projected, 1):
            m = re.search(r"algorithm\s*(\d+)", label, re.I)
            scenarios[f"Algorithm {m.group(1)}" if m else f"Algorithm {i}"] = df.reset_index(drop=True)
        return cls(actuals=actuals, scenarios=scenarios, flows=flows, assumptions=assumptions)

    # ---- what the variance engine asks of it ----
    @property
    def scenario_names(self) -> List[str]:
        return list(self.scenarios)

    def projection_months(self) -> pd.DatetimeIndex:
        first = next(iter(self.scenarios.values()))
        return pd.DatetimeIndex(first["month"])

    def sales_ratios(self) -> Dict[str, float]:
        """Shipping and taxes as a share of net sales, from the actual years: the
        forecast is Net Sales and the cash mechanics run on gross."""
        a = self.actuals
        net = float(a["net_sales"].sum()) or 1.0
        return {"shipping": float(a["shipping"].sum()) / net, "taxes": float(a["taxes"].sum()) / net}

    def repayment_rate(self, name: str) -> float:
        """Effective remittance per pound of gross: the sheet's own ratio when it
        has one, else repayment rate x Shopify share from the assumptions."""
        f = self.flows.get(name)
        if f is not None and "repayment" in f and "gross_sales" in f:
            g = f["gross_sales"].replace(0, np.nan)
            r = (f["repayment"] / g).dropna()
            if len(r):
                return float(r.iloc[0])
        rate = self.assumptions.get("repayment_rate", 0.18)
        share = next((v for k, v in self.assumptions.items() if k.startswith("shopify")), 0.82)
        return float(rate * share)

    def project_cash(self, name: str, gross_by_month: pd.Series) -> pd.DataFrame:
        """Rerun the scenario's cash mechanics on a different gross sales line.
        Overheads and the advance are the sheet's own absolute figures; the cost
        lines keep the sheet's month-by-month ratio to gross; the repayment is
        the effective rate on gross, capped by what is left of the loan."""
        f = self.flows[name].set_index("month")
        months = f.index
        gross = pd.Series(gross_by_month).reindex(months).astype(float)
        gross = gross.fillna(f["gross_sales"])
        rate = self.repayment_rate(name)
        loan = float(self.assumptions.get("total_loan_to_repay", f["loan_start"].iloc[0] if "loan_start" in f else 0.0))
        wc = 0.0
        out = []
        for m in months:
            g = float(gross[m])
            sheet_g = float(f.at[m, "gross_sales"]) or 1.0
            costs = {}
            for line in SCALING_LINES:
                ratio = float(f.at[m, line]) / sheet_g if line in f else 0.0
                costs[line] = ratio * g
            overheads = float(f.at[m, "overheads"]) if "overheads" in f else 0.0
            advance = float(f.at[m, "advance"]) if "advance" in f else 0.0
            repayment = min(loan, rate * g)
            loan -= repayment
            cash_in = g + advance
            cash_out = overheads + sum(costs.values()) + repayment
            wc += cash_in - cash_out
            out.append({"month": m, "gross_sales": g, "advance": advance, "overheads": overheads, **costs,
                        "repayment": repayment, "cash_in": cash_in, "cash_out": cash_out,
                        "net_cash": cash_in - cash_out, "working_capital": wc, "loan_end": loan})
        return pd.DataFrame(out)
