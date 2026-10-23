#!/usr/bin/env python3
"""Export a copy of the stock app's database as one JSON file, with the stock
app's own figures for that data, for tools/stock_import.py to convert and prove.

Runs with the STOCK APP's Python and code, never Reactor's:

    <stock app>/.venv/bin/python tools/stock_move/export_from_stock_app.py \\
        --stock-app <stock app folder> --database-url <url of a COPY> --out <file> [--now <iso>]

What it writes ("stock-export-1"):

- every table the stock app keeps, each as its columns, a count taken with
  SELECT COUNT(*) (independent of the rows written), its rows in primary key
  order, and `missing: true` when an older database has no such table.
  Timestamps become ISO 8601 in UTC (a value without a zone is UTC), bytes
  become base64, text holding JSON stays the text it is. Passwords are left
  out: logins are not carried over.
- `unknown_tables`: any other table in the database, with its count, so the
  proof can say so rather than leave it behind unnoticed.
- `bridge_rules`: the glass the production link matches Mono and HM lines
  to, which is a rule in the stock app's code rather than its data
  (`_GIZMO_FAMILY` in its app.py), read from the source as a literal, never
  by running it. Reactor keeps it in the stock sheet's settings, so this
  public repository names no glass or supplier.
- `sequences` (Postgres): the last id each table's sequence gave, which is
  ahead of the highest id left where rows were deleted at the top; the
  converter carries on after it.
- `expected`: what the stock app's analytics say about this data, with its
  clock pinned to `now` and its reads of the stock lines pinned to id order
  (it reads them in no order, and the order breaks ties in its sorted lists
  and orders its sums). The figures are worked out on an in-memory copy at
  the stock app's current schema, filled the way the stock app's own upgrade
  fills a column an older database lacks, so an old copy and a current one
  are treated alike. Its columns accept NULL, as the ones the upgrade added
  do in a long-running database.

It only reads: SQLite is opened read-only, a Postgres session is set read
only. The export holds real stock, prices and supplier contacts, so it is
written owner-only and refused anywhere inside a git working tree.
"""
import argparse
import ast
import base64
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

TABLES = ["items", "snapshots", "snapshot_items", "audit_log", "alerts", "backups", "meta", "periods",
          "users", "gizmo_bookings", "gizmo_usage_sheets", "gizmo_parked", "gizmo_aliases",
          "supplier_contacts"]
LEFT_OUT = {"users": {"password_hash"}}
# The tables the figures read, copied into the in-memory replica.
FIGURE_TABLES = ["items", "snapshots", "snapshot_items", "meta", "periods", "supplier_contacts"]


def inside_git_tree(path: str) -> bool:
    d = os.path.dirname(os.path.abspath(path)) if not os.path.isdir(path) else os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def to_json_value(v):
    if isinstance(v, datetime):
        return utc(v).isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(v)).decode("ascii")
    return v


def read_only_engine(url: str):
    from sqlalchemy import create_engine, event
    from sqlalchemy.engine import make_url
    u = make_url(url)
    if u.get_backend_name() == "sqlite":
        path = os.path.abspath(u.database or "")
        if not os.path.isfile(path):
            raise SystemExit(f"no database file at {path}")
        return create_engine("sqlite://", creator=lambda: sqlite3.connect(f"file:{path}?mode=ro", uri=True))
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _read_only(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        cur.close()
    return engine


def sequences(conn, present) -> dict:
    """The last id each Postgres sequence handed out (SQLite has none: it
    numbers after the highest rowid, which the converter does anyway)."""
    from sqlalchemy import text
    if conn.dialect.name != "postgresql":
        return {}
    out = {}
    for name in TABLES:
        if name not in present or name == "meta":
            continue
        seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": name}).scalar()
        if seq:
            last, called = conn.execute(text(f"SELECT last_value, is_called FROM {seq}")).one()
            out[name] = int(last) if called else int(last) - 1
    return out


def dump_tables(engine):
    """(the export's tables, the raw rows by table for the replica, the
    tables it does not know with their counts, the sequences)."""
    from sqlalchemy import MetaData, Table, func, inspect, select
    present = set(inspect(engine).get_table_names())
    out, raw, unknown = {}, {}, {}
    with engine.connect() as conn:
        for name in sorted(present - set(TABLES)):
            t = Table(name, MetaData(), autoload_with=conn)
            unknown[name] = conn.execute(select(func.count()).select_from(t)).scalar_one()
        for name in TABLES:
            if name not in present:
                out[name] = {"columns": [], "count": 0, "rows": [], "missing": True}
                raw[name] = None
                continue
            t = Table(name, MetaData(), autoload_with=conn)
            cols = [c.name for c in t.columns if c.name not in LEFT_OUT.get(name, set())]
            pk = list(t.primary_key.columns) or list(t.columns)
            rows = [dict(r._mapping) for r in conn.execute(select(t).order_by(*pk))]
            raw[name] = rows
            out[name] = {"columns": cols,
                         "count": conn.execute(select(func.count()).select_from(t)).scalar_one(),
                         "rows": [{c: to_json_value(r[c]) for c in cols} for r in rows],
                         "missing": False}
        seqs = sequences(conn, present)
    return out, raw, unknown, seqs


def figures(db, analytics, raw, now: datetime) -> dict:
    """The stock app's own analytics over an in-memory copy of the data."""
    from sqlalchemy import MetaData, create_engine, select
    from sqlalchemy.orm import sessionmaker
    replica = create_engine("sqlite://")
    # The stock app's tables, every column but the key accepting NULL: a
    # column its upgrade added (ALTER TABLE ... ADD COLUMN) does, and rows
    # may hold NULL there that its own NOT NULL schema would refuse.
    layout = MetaData()
    for t in db.Base.metadata.sorted_tables:
        for c in t.to_metadata(layout).columns:
            c.nullable = not c.primary_key
    layout.create_all(replica)
    tables = layout.tables
    with replica.begin() as conn:
        for name in FIGURE_TABLES:
            rows = raw.get(name)
            if not rows:
                continue
            t = tables[name]
            # SQLite keeps a timestamp's wall time and drops its zone: store UTC.
            conn.execute(t.insert(), [{c: (utc(v).replace(tzinfo=None) if isinstance(v, datetime) else v)
                                       for c, v in r.items() if c in t.c} for r in rows])

    real_select = analytics.select

    def select_in_id_order(*entities, **kw):
        st = real_select(*entities, **kw)
        return st.order_by(db.Item.id) if entities == (db.Item,) else st

    analytics.select = select_in_id_order
    analytics.now_utc = lambda: now
    session = sessionmaker(bind=replica, future=True)()
    try:
        S, P, C = db.Snapshot, db.Period, db.SupplierContact
        leads = {c.supplier: (c.lead_days or 0) for c in session.scalars(select(C)).all()}
        latest = session.scalars(select(S).order_by(S.taken_at.desc(), S.id.desc())).first()
        prev_totals = json.loads(latest.totals or "{}") if latest else None
        closed = session.scalars(select(P).where(P.closed_at.is_not(None)).order_by(P.closed_at, P.id)).all()
        pairs = [(p.id, "current") for p in closed] + [(a.id, b.id) for a, b in zip(closed, closed[1:])]
        return {
            "compute_current": analytics.compute_current(session),
            "reorder_suggestions": analytics.reorder_suggestions(session),
            "suggest_reorder_points": analytics.suggest_reorder_points(session, leads),
            "lead_by_supplier": leads,
            "fx_rates": analytics.fx_rates(session),
            "fx_revaluation": analytics.fx_revaluation(session),
            "totals_for_snapshot": analytics.totals_for_snapshot(session),
            "trends": analytics.trends(session),
            "forecast": analytics.forecast(session),
            "detect_anomalies": {"prev_snapshot_id": latest.id if latest else None,
                                 "alerts": analytics.detect_anomalies(session, prev_totals)},
            "compare": [{"left": l, "right": r, "result": analytics.compare(session, l, r)} for l, r in pairs],
        }
    finally:
        session.close()
        analytics.select = real_select


def glass_families(stock_app: str):
    """The stock app's `_GIZMO_FAMILY` ({"mono": glass, "hm": glass}) as
    its app.py assigns it, read as a literal without running anything;
    None when the app has no such rule."""
    try:
        with open(os.path.join(stock_app, "app.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_GIZMO_FAMILY"
                                                for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return None
            return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else None
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stock-app", required=True, help="the stock app's folder (its db.py and analytics.py)")
    ap.add_argument("--database-url", required=True, help="a COPY of the stock app's database")
    ap.add_argument("--out", required=True, help="the export file, outside every repository")
    ap.add_argument("--now", help="the instant the figures are worked out at (ISO 8601); default now")
    args = ap.parse_args(argv)
    if inside_git_tree(args.out):
        print(f"refused: {args.out} is inside a git working tree; the export holds real data", file=sys.stderr)
        return 2
    now = utc(datetime.fromisoformat(args.now)) if args.now else datetime.now(timezone.utc)
    # The stock app's db module makes an engine from DATABASE_URL when imported;
    # point it at nothing, so no code of the stock app's can reach the source.
    os.environ["DATABASE_URL"] = "sqlite://"
    sys.path.insert(0, os.path.abspath(args.stock_app))
    import db
    import analytics
    head = subprocess.run(["git", "-C", args.stock_app, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    tables, raw, unknown, seqs = dump_tables(read_only_engine(args.database_url))
    export = {"format": "stock-export-1", "exported_at": datetime.now(timezone.utc).isoformat(),
              "now": now.isoformat(), "source_head": head, "tables": tables,
              "unknown_tables": unknown, "sequences": seqs,
              "bridge_rules": {"glass_families": glass_families(args.stock_app)},
              "expected": figures(db, analytics, raw, now)}
    text = json.dumps(export, allow_nan=False, default=to_json_value)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    counts = ", ".join("%s %d" % (n, t["count"]) for n, t in tables.items() if not t["missing"])
    missing = ", ".join(n for n, t in tables.items() if t["missing"]) or "none"
    print(f"exported: {counts}; missing: {missing}" + (f"; NOT KNOWN: {unknown}" if unknown else "")
          + ("" if export["bridge_rules"]["glass_families"] else "; NO GLASS RULE for Mono and HM lines"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
