# Moving the stock sheet into Reactor

Two tools move the stock app's records into Reactor's own stores and prove
that nothing was lost or changed on the way.

1. `export_from_stock_app.py` reads a **copy** of the stock app's database
   and writes one JSON export: every table, and the stock app's own figures
   for that data. It runs with the stock app's Python and code, because it
   asks the stock app itself what its figures are.
2. `tools/stock_import.py` (run with Reactor's Python) converts the export
   into Reactor's stores in a folder of your choosing, then proves the result
   against the export: every record, every field, the history's checksum,
   every label code and barcode, and every figure to the penny. It exits 0
   only when the proof is empty.

3. `selfcheck.py` runs both on an invented database laid out as the stock
   app's upgrades leave a long-running one (columns added later accept
   NULL), with closed quarters, tied snapshots, every kind of warning and a
   table the move does not know. It is the check that Reactor's figures
   still match the stock app's own, which the test suite cannot run (it has
   neither the stock app's Python nor its code). Run it after any change to
   either tool or to `gizmo/stock_figures.py`:

   ```bash
   <stock app>/.venv/bin/python tools/stock_move/selfcheck.py \
       --stock-app <stock app> --reactor-python <Reactor's python>
   ```

## The export holds real data

Stock levels, prices, supplier contacts and who changed what. So:

- never commit an export, a converted folder or a proof report;
- never leave one inside any repository (both tools refuse to write there);
- delete them when the move is done.

The exporter only reads. A SQLite file is opened read-only and a Postgres
session is set read-only, but work from a copy all the same.

## Rehearsal on a local copy

```bash
mkdir -p ~/stock-move && cp <stock app>/stock.db ~/stock-move/stock.db
<stock app>/.venv/bin/python tools/stock_move/export_from_stock_app.py \
    --stock-app <stock app> --database-url sqlite:///$HOME/stock-move/stock.db \
    --out ~/stock-move/export.json
python tools/stock_import.py --export ~/stock-move/export.json \
    --people ~/stock-move/people.json --out ~/stock-move/stores --report ~/stock-move/proof.txt
```

`people.json` maps each username in the stock app's history to the Reactor
account it becomes: `{"username": "reactor account id"}`. The converter
refuses a history that names anyone without a mapping (`system`, `gizmo` and
`?` need none).

The stock app kept no orders, only each line's on-order figure and an
"ordered" history line per order placed. The converter rebuilds the orders
still outstanding from those lines (lines by one person for one supplier
and reference within a minute are one order; the newest await first) and
puts whatever on-order figure no line accounts for into one order per
supplier, marked as ordered before the move. The proof checks every line's
on-order figure equals what its rebuilt orders await.

An older copy may lack tables the stock app added later (the four tables of
the order link, the supplier contacts); the export marks them `missing` and
the figures fill any column it lacks the way the stock app's own upgrade
does.

### What the rehearsal showed (22 October 2026)

Run on a local copy of the stock app's database from July: the export, the
conversion and the proof all passed at the first attempt, every record,
field, label and figure matching. That copy predates the order link, so its
four tables were marked `missing`, and it had no closed quarter, so the
quarter comparison was proven only on the invented data in the tests. As a
check that the proof bites, one line's count was changed by one in a copy of
the converted stores: the proof named that line and field, and the figures
it moves.

## The real move

The same commands against a copy of the production database (a Postgres
dump restored locally, or a direct read-only URL), on the evening of the
switch. The steps around it are in plan 4 of the stock move.
