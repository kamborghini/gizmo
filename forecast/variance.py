"""Forecast vs actuals vs the plan, month by month, with the cash behind it.

For each month of the projection year the engine settles on one projected
figure: the actual for a closed month; actual-to-date plus the forecast for
the rest of the open month; the forecast for months inside the model
horizon; and beyond that, the scenario's own month scaled by how the store
has been tracking against it. Every scenario in the workbook gets a gap, a
verdict (on track, underrun, overrun) and a risk reading from the interval
(high when even the optimistic band misses the target, secure when even the
pessimistic band clears it). The projected line is then pushed through the
scenario's cash mechanics to give a working-capital and loan-balance path,
and any month that dips under the buffer is an alert.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .cashflow import CashFlowModel, month_start
from .config import Config


class VarianceEngine:
    def __init__(self, cfg: Config, cashflow: CashFlowModel):
        self.cfg = cfg
        self.cf = cashflow

    def monthly_view(self, actual_daily: pd.Series, forecast_daily: pd.DataFrame) -> pd.DataFrame:
        """actual_daily: date -> net sales (history to as_of). forecast_daily:
        date, p10, p50, p90 for the total level from as_of+1."""
        as_of = pd.Timestamp(self.cfg.as_of).normalize()
        a = pd.Series(actual_daily).astype(float)
        a.index = pd.DatetimeIndex(a.index)
        f = forecast_daily.copy()
        f["date"] = pd.to_datetime(f["date"]).dt.normalize()
        f = f.set_index("date")
        months = self.cf.projection_months()
        horizon_end = f.index.max() if len(f) else as_of
        rows = []
        for m in months:
            me = m + pd.offsets.MonthEnd(0)
            am = a[(a.index >= m) & (a.index <= me)]
            fm = f[(f.index >= m) & (f.index <= me)]
            actual_mtd = float(am.sum())
            lo, mid, hi = self._window_band(fm)
            if me <= as_of:
                method, p10 = "actual", actual_mtd
                p50, p90 = actual_mtd, actual_mtd
            elif m <= as_of:
                method = "actual_to_date + forecast"
                p50, p10, p90 = actual_mtd + mid, actual_mtd + lo, actual_mtd + hi
            elif me <= horizon_end:
                method = "forecast"
                p50, p10, p90 = mid, lo, hi
            elif len(fm):
                method = "forecast (partial) + extrapolated"
                covered = len(fm) / ((me - m).days + 1)
                p50, p10, p90 = mid / covered, lo / covered, hi / covered
            else:
                method, p50, p10, p90 = "extrapolated", np.nan, np.nan, np.nan
            rows.append({"month": m, "method": method, "actual_to_date": actual_mtd if m <= as_of else np.nan,
                         "projected_p10": p10, "projected_p50": p50, "projected_p90": p90})
        out = pd.DataFrame(rows)
        for name, sc in self.cf.scenarios.items():
            t = sc.set_index("month")["net_sales"]
            out[f"target|{name}"] = out["month"].map(t).astype(float)
        # months past the horizon: the scenario scaled by the trailing tracking ratio
        for name in self.cf.scenarios:
            tcol = f"target|{name}"
            known = out[out["method"] != "extrapolated"]
            ratio = 1.0
            if len(known):
                tail = known.tail(3)
                den = float(tail[tcol].sum())
                ratio = float(tail["projected_p50"].sum()) / den if den > 0 else 1.0
            out[f"tracking_ratio|{name}"] = ratio
        ext = out["method"] == "extrapolated"
        if ext.any():
            # use the first scenario's ratio for the point; widen the band by the ratio spread
            first = self.cf.scenario_names[0]
            out.loc[ext, "projected_p50"] = out.loc[ext, f"target|{first}"] * out.loc[ext, f"tracking_ratio|{first}"]
            out.loc[ext, "projected_p10"] = out.loc[ext, "projected_p50"] * 0.8
            out.loc[ext, "projected_p90"] = out.loc[ext, "projected_p50"] * 1.2
        for name in self.cf.scenarios:
            tcol = f"target|{name}"
            gap = out["projected_p50"] - out[tcol]
            out[f"gap|{name}"] = gap
            out[f"gap_pct|{name}"] = gap / out[tcol].replace(0, np.nan)
            out[f"verdict|{name}"] = [self._verdict(g) for g in out[f"gap_pct|{name}"]]
            out[f"risk|{name}"] = [("closed" if meth == "actual" else self._risk(lo, hi, t))
                                   for meth, lo, hi, t in zip(out["method"], out["projected_p10"], out["projected_p90"], out[tcol])]
        return out

    @staticmethod
    def _window_band(fm: pd.DataFrame, persistence_days: float = 4.0):
        """The band of a SUM of forecast days. Daily P10/P90 are the backtest's
        daily error quantiles; summing them as they stand assumes every day
        misses the same way, which is why a month came out with a band five
        times its width. Daily errors are neither independent nor in step:
        this takes them as persisting for about four days, so the relative
        band of an n-day sum is the daily band over sqrt(n / 4)."""
        if not len(fm):
            return 0.0, 0.0, 0.0
        mid = float(fm["p50"].sum())
        if mid <= 0:
            return float(fm["p10"].sum()), mid, float(fm["p90"].sum())
        rel_lo = float((fm["p10"] - fm["p50"]).sum()) / mid
        rel_hi = float((fm["p90"] - fm["p50"]).sum()) / mid
        n_eff = max(1.0, len(fm) / persistence_days)
        return mid * (1 + rel_lo / np.sqrt(n_eff)), mid, mid * (1 + rel_hi / np.sqrt(n_eff))

    def _verdict(self, gap_pct: float) -> str:
        if np.isnan(gap_pct):
            return "unknown"
        if gap_pct < -self.cfg.alert_pct:
            return "underrun"
        if gap_pct > self.cfg.alert_pct:
            return "overrun"
        return "on track"

    @staticmethod
    def _risk(p10: float, p90: float, target: float) -> str:
        if np.isnan(p10) or np.isnan(p90) or np.isnan(target):
            return "unknown"
        if p90 < target:
            return "high"
        if p10 >= target:
            return "secure"
        return "watch"

    def cash_view(self, monthly: pd.DataFrame, scenario: str) -> pd.DataFrame:
        """Push the projected net sales through the scenario's cash mechanics.
        Gross = net x (1 + shipping ratio + tax ratio) from the actual years."""
        r = self.cf.sales_ratios()
        gross = monthly.set_index("month")["projected_p50"] * (1 + r["shipping"] + r["taxes"])
        path = self.cf.project_cash(scenario, gross)
        path["below_buffer"] = path["working_capital"] < self.cfg.cash_buffer
        path["negative"] = path["working_capital"] < 0
        return path

    def alerts(self, monthly: pd.DataFrame, cash: Dict[str, pd.DataFrame]) -> List[dict]:
        out: List[dict] = []
        as_of = pd.Timestamp(self.cfg.as_of).normalize()
        for _, row in monthly.iterrows():
            if row["month"] + pd.offsets.MonthEnd(0) < as_of - pd.Timedelta(days=62):
                continue  # old closed months are history, not alerts
            for name in self.cf.scenarios:
                v, risk = row[f"verdict|{name}"], row[f"risk|{name}"]
                if (v in ("underrun", "overrun") and risk != "closed") or risk == "high":
                    out.append({"kind": "sales", "month": row["month"].strftime("%Y-%m"), "scenario": name,
                                "verdict": v, "risk": risk, "projected": round(float(row["projected_p50"])),
                                "p10": round(float(row["projected_p10"])), "p90": round(float(row["projected_p90"])),
                                "target": round(float(row[f"target|{name}"])), "gap": round(float(row[f"gap|{name}"])),
                                "gap_pct": round(float(row[f"gap_pct|{name}"]) * 100, 1), "method": row["method"]})
        for name, path in cash.items():
            for _, r in path.iterrows():
                if r["negative"] or r["below_buffer"]:
                    out.append({"kind": "cash", "month": pd.Timestamp(r["month"]).strftime("%Y-%m"), "scenario": name,
                                "verdict": "negative working capital" if r["negative"] else "below cash buffer",
                                "working_capital": round(float(r["working_capital"])), "loan_balance": round(float(r["loan_end"])),
                                "net_cash": round(float(r["net_cash"]))})
        return out

    def summary(self, monthly: pd.DataFrame, cash: Dict[str, pd.DataFrame], alerts: List[dict]) -> str:
        lines = [f"As of {self.cfg.as_of.isoformat()}: forecast vs the cash flow model"]
        names = self.cf.scenario_names
        head = f"{'Month':8} {'Method':32} {'Projected':>11} {'P10':>9} {'P90':>9} " + " ".join(f"{n[:6]+' gap':>12}" for n in names)
        lines.append(head)
        for _, r in monthly.iterrows():
            gaps = " ".join(f"{(r[f'gap_pct|{n}']*100):>+11.1f}%" if not np.isnan(r[f'gap_pct|{n}']) else f"{'n/a':>12}" for n in names)
            lines.append(f"{r['month'].strftime('%Y-%m'):8} {r['method'][:32]:32} {r['projected_p50']:>11,.0f} {r['projected_p10']:>9,.0f} {r['projected_p90']:>9,.0f} {gaps}")
        tot = monthly["projected_p50"].sum()
        lines.append("")
        for n in names:
            t = monthly[f"target|{n}"].sum()
            lines.append(f"Year: projected {tot:,.0f} vs {n} {t:,.0f} ({(tot - t) / t * 100:+.1f}%)")
        for n, path in cash.items():
            low = path.loc[path["working_capital"].idxmin()]
            lines.append(f"Cash ({n}): working capital bottoms at {low['working_capital']:,.0f} in {pd.Timestamp(low['month']).strftime('%Y-%m')}; "
                         f"loan left at year end {path['loan_end'].iloc[-1]:,.0f}")
        lines.append("")
        lines.append(f"{len(alerts)} alert(s)")
        for a in alerts[:20]:
            if a["kind"] == "sales":
                lines.append(f"  {a['month']} {a['scenario']}: {a['verdict']} ({a['gap_pct']:+.1f}%, risk {a['risk']}) projected {a['projected']:,} vs {a['target']:,}")
            else:
                lines.append(f"  {a['month']} {a['scenario']}: {a['verdict']} (working capital {a['working_capital']:,})")
        return "\n".join(lines)
