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

   On a throwaway Postgres as well, before the evening, so the exporter's
   Postgres path (a read-only session reading one snapshot, the sequences)
   has run once on invented data: start an empty Postgres database made for
   this, then add `--database-url postgresql://...` (that database) to the
   command above. The check creates the stock app's tables in it.

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

## The export from the live database

The exporter reads the live database directly, read only, every table from
one moment (one REPEATABLE READ transaction), so it can run on any day as a
rehearsal and changes nothing. Cameron runs it, on the Mac that has the stock
app's folder and its `.venv`:

1. Copy the stock app's database's public connection URL (the one that
   works from outside Railway) from its service in the Railway dashboard.
2. In a terminal, from this repository's folder:

   ```bash
   mkdir -p ~/stock-move
   read -rs STOCK_DB_URL && export STOCK_DB_URL
   <stock app>/.venv/bin/python tools/stock_move/export_from_stock_app.py \
       --stock-app <stock app> --database-url "$STOCK_DB_URL" --out ~/stock-move/export.json
   unset STOCK_DB_URL
   ```

   `read -rs` takes the pasted URL without showing it or keeping it in the
   shell's history.

The export is then moved in from Reactor itself (Settings, Move the stock
sheet in), which converts and proves it again on arrival. The steps of the
evening are under "The switch" below.

## The switch

On an evening agreed with the colleague, in this order. Steps marked
**Cameron** need the stock app's hosting or its database, which only he can
reach.

1. **Rehearse first, any day before.** Make the export (above) and, in
   Reactor, Settings, Stock sheet, **Move the stock sheet in**: send the
   export, match each stock app name to the person's Reactor account, and
   press **Check**. It converts the export into a folder of its own and
   proves every line, history entry, snapshot, quarter, warning, supplier,
   order and figure against the stock app's own; nothing changes. A
   difference is listed; fix the cause before the evening. Close the
   window: nothing is moved until **Move in**.
2. **Both stop editing stock.** Any counts on a phone are saved first (the
   workshop list's Save).
3. **Cameron: stop the stock app** in its hosting, leaving its database
   running. Nothing can change after this. Orders marked made in Reactor
   from now on wait in Reactor's queue for the stock sheet; they are booked
   into it once it has moved in (a booking applied twice changes nothing).
4. **Cameron: make the final export** (above), from the stopped app's
   database.
5. **In Reactor: Move the stock sheet in.** Send the final export, check the
   names, press **Check**, and once it says **Proven**, **Move in**. It
   converts and proves the same export again, puts exactly what it proved in
   place, and only then puts the stock sheet live: the Stock tab opens for
   the people matched and the first stock backup is made. The orders that
   waited are booked on Reactor's next regular round, within about fifteen
   minutes. If anything after going live does not finish, the window says
   which step, and it is finished the next time the window or Settings is
   opened.
6. **Look.** Scan a few shelf labels on a phone, and check the Overview
   against the stock app's last screen. Until the orders that waited are
   booked (step 5), the Overview is higher by exactly their glass.
7. **Afterwards.** Leave the stock app switched off and keep its database
   (and the final export, outside every repository) until the next quarter
   close; switching back is possible only in the first few days, re-entering
   by hand anything done in Reactor since. Delete the export and the
   converted folders from the Mac. Once the phones scan well on the Stock
   tab, the camera test in Settings comes out.
