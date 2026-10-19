# Switches, fields and names

**Approved 19 Oct 2026.** Stage 3, piece 3 of the 14 October engineering
audit. Cameron approved all three parts after the before-and-after photo of the
Edit order window, including the larger captions on the dispatch and CRM forms.

## Why

- **Switches.** `switchBtn()` already builds a real switch (a button with the
  switch role that says its state). The five switches written into Settings
  (four preferences and auto-refresh) are bare boxes with no name a screen
  reader can read; they work only because `syncToggles` stamps a role and a
  state on them after drawing, and a page-wide key handler presses them.
- **Fields.** The field itself has one look (applied to the element), but its
  caption has two: the house label (14 medium, primary ink) in Settings, the
  question windows, Team, Products and Skills, and a 12 grey caption
  (`disp-fld-lab`, `disp-addr-lab`) in the dispatch, new-shipment, edit-order
  and CRM forms. The four wrappers (`pfield`, `disp-fld`, `disp-addr-f`,
  `sk-field`) share one layout.
- **Names.** Asked of the browser on every measured screen and 13 windows,
  these controls have no name a screen reader reads: the CRM Contacts row
  checkboxes (the record's 30 `label` findings), the report question box on
  every report screen, the CRM deal's note box, the dispatch manifest's and
  stock usage's date and quantity fields, the new-shipment and edit-order paste
  boxes and parcel sizes, the shipping-settings credentials and box rows, the
  Settings sign-off box and the five Settings switches. Most are named only by
  a placeholder, which goes as soon as someone types.

## What changes

### Switches

`switchBtn(label, on, onToggle)` stays the part for a switch built in the
script, and gains `setSwitch(sw, on)`, which sets the look (`on`) and the state
(`aria-checked`) together. The Settings switches become buttons in the page's
markup with the switch role, their state, and a name from the title beside
them (`aria-labelledby`, the line under it as `aria-describedby`); the
Settings code flips them with `setSwitch`. `syncToggles`, its share of the
batched observer and the page-wide Enter/Space handler are deleted. **No
visible change.**

### `field(caption, control, opts)`

Builds `<label class="pfield[ cls]"><span>caption</span>control</label>`, with
`opts.help` as a line under the control (`field-help`) and `opts.cls` for a
screen's layout hook. The control may be added afterwards, as the call sites do
today. Every captioned field moves to it: `pfield` (22 sites), `disp-fld` (15),
`disp-addr-f` (4, including CRM's `crmField`) and `sk-field` (5), the old
family class kept as `cls`. `disp-fld-lab` and `disp-addr-lab` are retired.
**Visible change**: the dispatch, new-shipment, edit-order and CRM forms'
captions become the house label (14 medium, primary ink), as in the photo.

### Every control named

Each control in the list above gets a real name: an `aria-label`, or a caption
through `field()`, or for the Settings boxes the label beside them. List
checkboxes are named for their row ("Select Marcus Bell").

## Guards

- A page-suite guard fails if any section other than the parts builds a label
  wrapper of the four families by hand, or a `.toggle`.
- `syncToggles` and the page-wide toggle key handler stay gone.
- The browser suite checks, with zero tolerance, that every visible input,
  select, text box and switch on every measured screen and in every window the
  keyboard journeys open has a name (its label, `aria-label`,
  `aria-labelledby` or `title`; for a button, also its words).
- The record's `label` findings go to zero and the record is lowered.
- Before-and-after screenshots of the 108 states: only the states with a
  converted caption or a newly named control may differ.

## Documentation and release note

`docs/DESIGN.md` gains Switches, Fields and Names under Parts. One release
note, dated the merge day: field captions in the dispatch and CRM forms match
the rest of the app, and every switch, box and tick has a name a screen reader
reads out.

## Not in this piece

Rows of a tick and its words (Team's tab picker, dispatch's insurance and
notify ticks, CRM's checklist lines) are a family of their own and go with
tables and rows (piece 4). The look of the field itself does not change.
