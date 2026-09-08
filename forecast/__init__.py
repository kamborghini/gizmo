"""Reactor forecasting: multi-level sales prediction with cash-flow variance.

A batch package, deliberately separate from the Starlette app: it has its own
requirements (numpy, pandas, openpyxl, scipy, scikit-learn, LightGBM; CatBoost
and PyTorch optional) and is never imported by the server. Run it with
``python -m forecast --help``.
"""
__all__ = ["config", "calendar", "cashflow", "ingest", "features", "backtest", "reconcile", "variance", "pipeline"]
