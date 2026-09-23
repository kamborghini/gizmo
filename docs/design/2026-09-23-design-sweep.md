# Design sweep, 23 September 2026

Cameron, 2026-09-23: "we still have a lot of the design that looks unintentional and un thought out", with screenshots of the Reconciliation connection card, the Forecast overview and chart, and the forecast's "Why" breakdown.

## How it was done

- The app was run locally on scratch stores with sample data for every screen (a fixture Shopify, a seeded forecast run, reconciliation, inbox and CRM), and every screen was photographed at 1728px (Cameron's laptop width) and at 390px.
- Four independent reviewers each took one group of screens and listed everything that looked unintentional, with a screenshot or a measurement and the line of code behind it: 159 findings. A fifth checked the result.
- Where one fault had several instances it was fixed at its source: money and dates are written one way everywhere, chips have a neutral base, card children keep the 16px gutter, the chart legend draws each mark as it is drawn, the production queue is laid out by its own width, a failed refresh keeps the last good report, and every confirm names its action.
- Every changed rule that a guard pinned was re-pinned to the new behaviour, and new guards cover the three screens Cameron sent.

## The independent check

The fifth reviewer re-measured every finding on the changed app. It confirmed 138 fixed, and found 17 not fixed or only partly fixed and 16 new faults the changes had made. All of them were then put right and measured again in the same rig:

- The months-ahead chart had lost its only key for the dashed line and the shaded range: the legend now draws whenever there are two lines, a dashed line or a range, and never for one plain line.
- The Worth looking at rows sat 16px further in than the button under them; the setup steps' numbers hung into the card edge; Show more touched a skill card's border; the keyword scan's summary touched its card's border.
- The small-field class lost to the field recipe, so fields stayed 32px beside 28px buttons; Not checked still rendered as a 24px headline; the phone drawer still showed the feature card; several touch controls were under 32px.
- The product plan had no Refresh, because the plan carries no product id: it now uses the id it was opened with.
- With nothing owed, the Liability card still showed its search and filters over an empty list; it now says only that nothing is owed.
- The forecast month table stacked 'May 2026' over two lines on a phone; the reconciliation arithmetic heading still carried its bracket; the source blurbs in the Why card began without a subject.
- The production queue's shared columns started only at 860px of list, so a refunded order's date jumped on a tablet: they now start at 560px (measured at a 1024 window, every date ends at the same pixel).
- The Size list paged by lines, maker headings included ('Page 1 of 22' for 1,946 models at 100 a page): it now pages by models (Page 1 of 20). Save and Cancel in its editor no longer stack.
- The master's row on Team ended its details 300px right of everyone else's: the list now shares one set of columns.
- The Backups row squeezed its words into a sliver and ran off a phone's settings window: its buttons now take their own line. Two settings captions pointed at the wrong place.
- On a phone Overview, sparkline tiles were half width beside stretched plain tiles: a tile with a sparkline now takes the row.
- The Finance tab strip was cut off on a phone once Beta moved into the tabs: it scrolls, and the tab Beta marks drop on a phone (the sidebar keeps them).
- Smaller: a global variable leaked from the Collections window; the email help lines looked like labels and Cc / Bcc sat centred; the feature form's two fields sat at different distances from their labels; the Customers run gate touched the card below; Save sign-off touched its field; every empty CRM chart said deals would fill it; a sentence sat in the SEO score's figure column; an amber figure carried a red pill.

A sweep of all twenty screens at 1728px and at 390px with touch then found no overflow, no clipped text and no console errors.

## The findings

Severity: high = seen within five seconds of opening the screen; medium = seen on use; low = polish. Line numbers in the evidence refer to the code before this sweep.


### Finance: Forecast, Reconciliation, Liability, Xero sync

| ID | Severity | What looked unintentional | Outcome |
|---|---|---|---|
| A01 | high | The mailbox address field is 160px tall and touches the card edge, and the Connect button stretches the full 1395px card (recon (Accounts mailbox not connected card)) | Fixed. |
| A02 | high | The 'Last run failed' card stretches its chip into a 1395px pink bar, and the sentence sits flush against the card border (forecast (a nightly run failed but an older run exists)) | Fixed. |
| A03 | medium | A severity tile's number and the list it filters disagree: Medium says 1, and clicking it lists '2 discrepancies' (recon) | Fixed. |
| A04 | medium | 'Within terms' is £2,119 on the tile and £1,200 in the Aged debt legend, and the tile's own filter shows £1,200 (liability) | Fixed. |
| A05 | medium | A filtered customer row keeps the whole account's figures while its count follows the filter (liability (a status filter applied)) | Fixed. |
| A06 | medium | 'Today' and 'This week' draw the same seven days and the same total (forecast (Cash in: Today and This week)) | Changed rather than removed: Today keeps its seven days but its headline is today's figure against the average of the six before, so it is no longer the same view as This week. |
| A07 | medium | 'Last 3 months' also draws three months of forecast ahead and adds them into its 'last three months' total (forecast (Cash in: Last 3 months)) | Fixed. |
| A08 | medium | Custom range with no dates draws all 420 days of history day by day under 'The range you chose'; its From and To fields sit 765px below the tab and are too narrow for a date (forecast (Cash in: Custom range)) | Fixed. |
| A09 | medium | The chart legend names series that draw nothing (forecast chart (every range)) | Fixed. |
| A10 | low | One chart has two keys that describe the same marks in different words (forecast chart) | Fixed. |
| A11 | medium | The two alert rows sit 32px inside the card while the 'See all 8' button under them sits at 16px (forecast (Worth looking at)) | Fixed. |
| A12 | medium | The table's explanation never says 'The next 6 months are shown', describes rows that are not there, and points 'below' at alerts that are above (forecast (Every source, side by side)) | Fixed. |
| A13 | low | More copy that points 'above' at a list it is not in, the same fault as the known Theta sentence (forecast (How much to trust it; How each one works)) | Fixed. |
| A14 | low | The provenance sentence stops at 'reported against.' and the next line gives the run date in ISO (forecast (The plan it is judged against)) | Fixed. |
| A15 | medium | Dates appear in three formats on the same screens (recon, forecast, liability, connector) | Fixed. |
| A16 | medium | One discrepancy status is written four ways, and the filter has no 'Corrected' (recon (status)) | Fixed. |
| A17 | medium | The evidence is a raw JSON dump labelled with internal ids (recon (opened discrepancy)) | Fixed. |
| A18 | medium | The detail panel repeats the row directly above it (recon (opened discrepancy)) | Fixed. |
| A19 | medium | Heading sizes are inverted: the discrepancy's own title is 14px and its sub-sections are 16px (recon (opened discrepancy)) | Fixed. |
| A20 | medium | At phone width the Close button is off-screen and the AI-scan chip runs past the panel (recon (opened discrepancy, phone 390)) | Fixed. |
| A21 | low | The same AI-scan warning is 'AI-read scan' on the row and 'READ BY AI FROM A SCAN - UNVERIFIED' in the detail (recon) | Fixed. |
| A22 | medium | The sweep notes shown under the live connection pills are from the last sweep and contradict them (recon (connection card)) | Fixed. |
| A23 | medium | Raw enum and code words reach the screen in more places than the known alert row (forecast, recon, connector) | Fixed. |
| A24 | medium | The Gap column reads the rounded fraction, so it disagrees with the Alerts drawer on the same page (forecast (Month by month table)) | Fixed. |
| A25 | low | Chips given no tone render as bare bold words, not pills (forecast, recon, liability) | Fixed. |
| A26 | low | Chip text uses three casings across the Finance tabs (forecast, recon, liability, connector) | Fixed. |
| A27 | low | The day unit is written four ways (liability) | Fixed. |
| A28 | low | Tile colours are fixed rather than read from the values: 'Due soon £0' is amber while 'Overdue £0' is green (liability) | Fixed. |
| A29 | low | 'Overdue' and 'Overdue orders' are the same filter, so one click ticks both tiles (liability) | Fixed. |
| A30 | low | The Aged debt card has 33px of space below the legend and 17px above the title (liability (Aged debt card)) | Fixed. |
| A31 | low | The empty state keeps the full filter toolbar, an instruction to 'open one', and 'Oldest debt 0 days' (liability (nothing owed)) | Fixed. |
| A32 | low | 'order(s)' is the only unpluralised count on the page, and on a phone the borrowed strip squeezes its title into three lines (liability (Paid but still tagged strip)) | Fixed. |
| A33 | low | While loading, the page is titled 'Liability' with no Finance tabs, then changes to 'Finance' with tabs (liability (loading)) | Fixed. |
| A34 | medium | Check results are crushed to about 60px of text: 'Would create invoice INV-104300' shows as 'Would cr…' (connector (One order results)) | Fixed. |
| A35 | low | The three tiles' input rows stop lining up once any tile shows a result (connector (Review and send tiles)) | Fixed. |
| A36 | medium | In the settings form, help text takes a grid cell of its own, so the two-column grid alternates between field and help and field and field (connector (Settings, opened)) | Fixed. |
| A37 | medium | The 'Link the connector service' card is built from settings-list classes at 14px and 12px, capped to 414px in a 1397px card, and uses the app's old name 'gizmo' (connector (service not linked)) | Fixed. |
| A38 | low | Some disabled controls give no reason, while their siblings do (connector, recon, forecast) | Fixed. |
| A39 | low | Money is written two ways in one tile: 'GBP 1842.50' beside '£1,842.50' (connector) | Fixed. |
| A40 | low | The Mode chip 'Send' is painted success green, like the Outcome 'Clean' beside it (connector (runs table)) | Fixed. |
| A41 | low | A figure and its pill disagree in colour, and a month the table calls 'on track' gets a red pill (forecast (Where things stand, Algo 2 and Algo 3)) | Fixed. |
| A42 | low | The same fact is phrased two ways in neighbouring cards: 'plan £19,698' and 'plan is £234,269' (forecast (Where things stand)) | Fixed. |
| A43 | low | Source column headings are cut at 22 characters with no way to read them, and the same error prints as '+3.0%' in one table and '3%' in the next (forecast (What each source said before the month began)) | Fixed. |
| A44 | low | Frames are nested three deep in some drawers but not in others (forecast drawers, recon detail, connector tiles) | Fixed. |
| A45 | low | The 'Compare sources on the chart' card title is styled as grey body text (forecast (Cash in)) | Fixed. |
| A46 | low | The section is 'Worth looking at' but its 'See all 8' button opens a drawer called 'Alerts (8)' (forecast) | Fixed. |
| A47 | low | 'How certain is that?' is a full bordered card holding one sentence, where the design comment asks for a quiet line (forecast (Where things stand)) | Fixed. |
| A48 | low | Two paragraphs in one card are set to different widths: 1395px, then 631px (forecast (Why the forecast is what it is)) | Fixed. |
| A49 | low | The last two x-axis dates overlap at phone width (forecast (phone 390)) | Fixed. |
| A50 | low | The top bar's Beta tag touches the page name with no gap (top bar (Forecast, Reconciliation, Xero sync)) | Fixed. |
| A51 | low | The shared 'Finance' heading gains and loses a Beta tag as you switch tabs (Finance hero (all four tabs)) | Fixed. |
| A52 | low | The setup steps say 'set the variables and redeploy' three times (recon (Connect Xero setup card)) | Fixed. |

### Reports: Overview, SEO, Keywords, Products, Customers

| ID | Severity | What looked unintentional | Outcome |
|---|---|---|---|
| B01 | high | Money is printed four different ways, often on the same screen: '4,366 GBP', '£34,927', '29k GBP', and a bare '7634' (customers, overview, keywords, products (shared)) | Fixed. |
| B02 | high | Three different average order values on one screen; the chart's '261 GBP' is a figure that never happened (overview) | Fixed. |
| B03 | high | The y-axis on small counts prints the same number twice ('0, 1, 2, 2, 3') and places the rules at values it does not label (products (product detail), customers) | Fixed. |
| B04 | medium | The product plan page is not assembled like any other report: bare headings, a stack of loose cards, detail boxes 24px apart, and two KPI tiles in a four-column row (products (product detail)) | Fixed. |
| B05 | medium | Charts give no time window while the KPI beside them names a different one, so the same metric shows two unexplained numbers (products (product detail), customers) | Fixed. |
| B06 | medium | The source line under every chart figure opens with a legend-style dot that keys nothing, and it switches between black and grey by chart type (overview, seo, customers, products (all charts)) | Fixed. |
| B07 | high | The keyword scan URL field and the product Tag filter show the browser's default bevelled 2px border instead of the app's field style (keywords, products (filters)) | Fixed. |
| B08 | medium | The scan card is double-padded and built from the Memory page's knowledge-card classes: content sits 16px inside every other card's edge, and its title is a size below the page's other card titles (keywords) | Fixed. |
| B09 | medium | A scan result is a stack of framed cards inside the scan card, with sub-headings larger than the card's own title (keywords (scan result)) | Fixed. |
| B10 | high | Trade radar is hand-built from the size-check's classes: its title is smaller than its sub-headings and pushed down by default h3 margins, its description is shoved to the far edge, and there are 32-40px gaps around one-line sentences (customers) | Fixed. |
| B11 | low | Numeric column headers in the radar tables are left-aligned over right-aligned figures (customers) | Fixed. |
| B12 | medium | 'Recommended actions' is a bare 16px label outside its card, between two 18px section headings; every other report makes the same list a card title (overview) | Fixed. |
| B13 | medium | The report's detail sections tack onto the end of 'What's notable' with no heading and no rule, and their prose runs full width while the insights above stop at 482px (overview) | Fixed. |
| B14 | medium | Raw enum and code words reach the screen: lowercase 'high/medium/low' pills, 'active' on every product row, lowercase filter options, '>=' and ISO dates in chips, and 'HTTP None' (overview, seo, keywords, customers, products) | Fixed. |
| B15 | medium | SEO checks contradict themselves when no pages were sampled: '0% of sampled' in warning colour opens 'Every one of the 0 sampled pages has a meta description' (seo) | Fixed. |
| B16 | low | The red score is the one figure on the SEO page that cannot be opened, and its bar stays black whatever the score (seo) | Fixed. |
| B17 | medium | KPI rows end in orphans or holes, and Keywords shows two different KPI designs on one page (keywords, customers, products (detail), overview) | Fixed. |
| B18 | medium | On a phone every KPI tile takes a full row: Overview's seven cost 1,237px before the first chart (overview, customers (phone)) | Fixed. |
| B19 | medium | The Customers sector picker is a one-option control reading 'Comprehensive' with an unexplained green dot, and it appears on the Keywords loading screen too (keywords (loading), customers) | Fixed. |
| B20 | medium | Before the report is run, Customers opens on a lone chip and the trade radar, and the Run button sits below the fold (customers (run gate)) | Fixed. |
| B21 | medium | Whole cards hold a single centred sentence, and one of them keeps a working 3M/6M/12M/24M control for a chart that is not there (seo, keywords) | Fixed. |
| B22 | medium | 'Traffic by channel' leaves 237px of empty card under its four bars, and its 'last 12 months' label is not true (overview (GA4 connected)) | Fixed. |
| B23 | medium | The copy uses American spelling against the British English rule: 'optimization', 'Analyzing', 'catalog', 'Customize' (overview, seo, keywords, customers, products) | Fixed. |
| B24 | medium | A failed refresh throws away the report and leaves a dead end: an error box with no Try again and no Refresh button (overview, seo, keywords, customers, products) | Fixed. |
| B25 | low | The PDF button is missing after 'Load products' until you leave and come back, and the printed report keeps the Refresh icon (products) | Fixed. |
| B26 | low | The search field's clear (×) button shows while the field is empty (products) | Fixed. |
| B27 | medium | The custom period menus list every month name twice with no year, so 'Apr to Sep' is ambiguous (products) | Fixed. |
| B28 | low | 'Top products by revenue' says 'The six that earned most' above three or five bars (products) | Fixed. |
| B29 | low | The compare-periods chip is a solid black pill, against the neutral-tint change chip Cameron chose for KPIs (products) | Fixed. |
| B30 | low | An empty filters holder adds a second 16px gap between the toolbar and the first product row (products) | Fixed. |
| B31 | low | The header's Customize button appears and disappears as you type in product search (products) | Fixed later the same day: a search or filter that leaves fewer than two earners keeps the Top products card, which says there is nothing to rank, so the page keeps its two cards and Customise stays. |
| B32 | low | On each action row the Track button hangs 4px below the checkbox, text and priority pill (overview, seo, keywords, customers, products) | Fixed. |
| B33 | low | The 'Open follow-ups' card has 36px of empty space under its last row from an inline margin (overview) | Fixed. |
| B34 | low | One metric is named three ways on one screen, and the same percentage is formatted two ways (overview, customers) | Fixed. |
| B35 | low | KPI icons are mismatched: 'Products' and 'Units sold' show the app's own bolt logo as a fallback, Orders and Low stock share one glyph, and the Filters button uses the search magnifier (overview, seo, keywords, products (detail), customers) | Fixed. |
| B36 | low | Loading screens say the same thing twice, in the subtitle and in the spinner line (overview, seo, keywords, customers, products (loading)) | Fixed. |
| B37 | low | Capped prose leaves stranded words: 'for ten.' and 'it' alone on their own lines (overview, seo, keywords, customers, products (detail)) | Fixed. |

### Operations: Production Manager, Size list, Loan units, CRM, Inbox, Files

| ID | Severity | What looked unintentional | Outcome |
|---|---|---|---|
| C-01 | high | Opening a label preview makes the row buttons paint over the item line and hide the date (labels (To make; any queue) at 1728 with an order's Preview open) | Fixed. |
| C-02 | medium | Queue columns do not line up from row to row; the refunded row's item line and date jump about 121px to the right (labels (To make and Unprocessed) at 1728) | Fixed. |
| C-03 | medium | The card title and the 'All' filter give two different counts for the same list (labels (To make, Unprocessed)) | Fixed. |
| C-04 | medium | The Custom Shipments tab is built from an older kit and does not match the other four tabs (labels > Custom Shipments tab) | Fixed. |
| C-05 | low | Buttons and fields of different heights sit side by side (labels (To make) with a stale row; loans Chasing; size list inline editor and pager; crm Pipedrive panel) | Fixed later the same day: the production queue's row buttons are the small control too (28px, 36px on touch), square when they drop to icons. |
| C-06 | medium | The table head crams 'Models' against '1,946 models', which repeats the word (sizes) | Fixed. |
| C-07 | medium | Figures in 'Produced as, mm' do not line up; they move left whenever a chip follows (sizes) | Fixed. |
| C-08 | low | Status chips are raw lowercase words, and one row can carry two amber chips for one state (sizes) | Fixed. |
| C-09 | medium | The Size list pages with its own pager: 'lines' where the page counts models, and a select whose caret is drawn over its label (sizes (table foot)) | Fixed. |
| C-10 | medium | The Chasing card is laid out unlike its siblings: a loose heading gap and one field boxed inside the card (loans) | Fixed. |
| C-11 | medium | 'On the shelf 0' and 'Everything is on the shelf.' on the same screen (loans (empty register)) | Fixed. |
| C-12 | medium | All three Loans KPIs wear the same placeholder lightning icon (loans) | Fixed. |
| C-13 | medium | The Insights KPIs are Liability's tiles: sentences set as figures, a green £0, and a tile row that stops short of the charts (crm > Insights) | Fixed. |
| C-14 | low | Chart cards side by side have ragged heights, and their empty state is a small left-aligned footnote (crm > Insights) | Fixed. |
| C-15 | medium | The period switch shows two selected segments at once when Mine is on (crm > Activities) | Fixed. |
| C-16 | medium | The Board/List switch and the '10 Deals' title ignore the status filter (crm > Deals) | Fixed. |
| C-17 | medium | The board's coloured dots have no key, and the red one reads as the 'untouched too long' red (crm > Deals (board)) | Fixed. |
| C-18 | low | One action, two renderings: the column '+ Deal' uses a typed plus, the header '+ Deal' an icon (crm > Deals (board)) | Fixed. |
| C-19 | low | The fifth column is cut off mid-word at Cameron's width (crm > Deals (board) and mail (board)) | Fixed. |
| C-20 | low | Counted titles in Title Case ('10 Deals', '0 Leads', '10 Organisations', 'Custom Shipments') beside sentence case elsewhere (crm (Deals, Leads, Activities, Contacts) and labels tabs) | Fixed. |
| C-21 | low | The To ship queue offers a 'Not made' filter that can only ever be empty (labels > To ship) | Fixed. |
| C-22 | low | A raw Shopify tag code in the copy: 'Orders tagged "IP".' (labels (To make)) | Fixed. |
| C-23 | low | Icons reused for unrelated actions, including a tick that reads as a selected menu item (labels (card head, toolbar, More menu)) | Fixed. |
| C-24 | low | The 'Updated just now' stamp and its Refresh are split between the page header and the card (labels) | Fixed. |
| C-25 | low | The list and the board age the same email differently, and the page legend fits only the board (mail) | Fixed. |
| C-26 | low | The sync banner ends on a dangling 'since' (mail (sync warning banner)) | Fixed. |
| C-27 | low | The Who is on today card has 27px under its strip against 17px over its head (mail (Who is on today)) | Fixed. |
| C-28 | medium | The compose form is stacked with no spacing, and its address rule sits under Send (mail > Compose (New email window)) | Fixed. |
| C-29 | low | Thread details are set in the settings help class, so the sender line is capped and orphans 'ago' (mail > open a thread) | Fixed. |
| C-30 | low | The thread's Assign select borrows the presence-chip class and offers 'Nobody (release)' on an email nobody holds (mail > open a thread (assign row)) | Fixed. |
| C-31 | low | On a phone the bulk bar puts its checkbox alone on one line and the hint on the next (mail at 390 wide) | Fixed. |
| C-32 | medium | The Files setup card uses another screen's heading and an inline-styled 12px paragraph, under a meter for storage that does not exist (files (storage not connected)) | Fixed. |
| C-33 | low | The Beta tag touches the page name in the top bar (crm (top bar); also Reconciliation, Forecast, Xero sync top bars) | Fixed. |
| C-34 | low | Capital letters used for emphasis and labels in sentence-case copy (mail Filters window, labels Edit order window, crm drag bar) | Fixed. |
| C-35 | low | Internal wording in the Size list header and columns: 'shipped copy', 'Under, mm' (sizes (header, table head)) | Fixed. |

### Workspace, shell and phone: Team, Memory, Skills, Chat, Guide, Settings

| ID | Severity | What looked unintentional | Outcome |
|---|---|---|---|
| D1 | high | Release notes and feature-request rows sit flush against the card's border, with no 16px gutter (guide (What's new and Requests tabs)) | Fixed. |
| D2 | high | Prose is capped at 52ch inside full-width cards, so it fills the left third and leaves a large blank to its right. The whole Guide is also set in 12px Settings sub-text. (guide, memory, settings modal) | Fixed. |
| D3 | high | Note type chips print raw lowercase enum slugs, and the 'insight' one renders as a grey padded box because its class collides with the chat .insight card (memory (notes), chat (reply actions)) | Fixed. |
| D4 | medium | Cards that add their own padding on top of the card gutter inset their content by 32px instead of 16px (memory, skills (also keywords)) | Fixed. |
| D5 | medium | The focused composer draws two focus rings, one on the box and a second, differently rounded one on the textarea inside it (chat) | Fixed. |
| D6 | medium | At phone width, a starter suggestion wraps to two lines inside a fixed 28px pill and spills over its top and bottom edges (chat (phone)) | Fixed. |
| D7 | medium | The chat history list sits entirely below the fold of the sidebar at laptop height, and the scrollbar is hidden, so nothing shows it exists (shell sidebar (chat), phone drawer) | Fixed. |
| D8 | medium | Nav icons are reused for different sections, and one is an 'info' glyph standing in for Forecast (shell sidebar and search panel) | Fixed. |
| D9 | medium | Every connection row gets a Connected/Needs setup/Not connected pill even when that is not what the row measures, raw server text reaches the screen, and the backup buttons are stranded under the last row (settings modal (Connections)) | Fixed. |
| D10 | medium | One modal uses four different ways to save, identical switches behave differently, and the profile fields are filled a darker grey than a disabled field (settings modal) | Fixed later the same day: every switch saves the moment it changes (the server merges the switches into the stored profile, so a switch never sends text), each block of text has its own Save under it, the footer is gone, and the Overview is recomputed on close only if something changed and it had been run. |
| D11 | low | The profile placeholders are generic US-store copy in dollars, and '&' appears where the rest of the app says 'and' (settings modal, memory) | Fixed. |
| D12 | medium | American spellings break the British English decision, including the Customize button on every widget page (memory, skills, and every report page (shell hero)) | Fixed. |
| D13 | medium | The assistant was renamed Reactor, but ten on-screen strings still call it 'the copilot' or 'your store copilot', and Chat's empty state speaks as 'I' (chat, memory, skills, settings) | Fixed. |
| D14 | medium | The topbar title and the page heading give the same page two different names on 9 of 20 screens (shell topbar across screens) | Fixed later the same day: every page is headed with its sidebar name (Overview, SEO, Keywords, Customers, Memory, Liability, Reconciliation, Forecast, Xero sync), in every state including the Run gate, and the printed report's header uses the same names. |
| D15 | medium | The per-person Tabs panel is one wrapping row of inline-styled pieces: a 1,360px select for a colour, orphan permission lines, and 'Everything' and 'Save' far from what they act on (team (People, Tabs panel open)) | Fixed. |
| D16 | medium | Work and Activity drop the card structure the People tab uses, and the payroll export has two unlabelled date fields (team (Work and Activity tabs)) | Fixed. |
| D17 | medium | When a read fails, Team replaces the whole page, title included, with a bare red strip and no Try again (team, team Work tab, guide What's new and Requests) | Fixed. |
| D18 | low | The master's row is shorter than the others and shows its role as grey meta text, so the role column and the meta column do not line up (team (People)) | Fixed. |
| D19 | medium | Ten confirmation dialogs are titled 'Please confirm' with a 'Confirm' button, rather than naming the action (team confirms (and other screens)) | Fixed. |
| D20 | medium | Release notes are cut mid-word at 400 characters, and the note text starts at a different indent after each kind chip (guide (What's new)) | Fixed. |
| D21 | medium | The request state is shown twice in two formats, the primary button is glued to the heading, and one action has three names (guide (Requests)) | Fixed. |
| D22 | low | In the feature-request modal, the one-line field is half width, the details box is full width with no label, and both are built from other screens' classes (shell (Ask for a feature modal)) | Fixed. |
| D23 | medium | The page search shows Chromium's saturated blue clear 'x'. The app already suppressed it once, for table search only. (shell (Search panel)) | Fixed. |
| D24 | low | Dates and times use two formats and two clocks on the same screens (memory, team Activity) | Fixed. |
| D25 | low | Failures in Memory, Skills and several other places appear as neutral notices, and the toast stack covers the topbar's controls (shell toasts) | Fixed. |
| D26 | low | The account menu opens upward over the support card, leaving the card's heading showing above the menu (shell (account menu)) | Fixed. |
| D27 | low | An unexplained black dot sits on Guide and stays after Guide is opened (shell sidebar) | Fixed. |
| D28 | low | The Guide's header action is a 32px button, while every other page-header action is 28px (guide header) | Fixed. |
| D29 | low | Team's footnotes run as a single 1,300px line of 12px text outside the card, the opposite of the capped help text elsewhere (team (all three tabs)) | Fixed. |
| D30 | low | The starter password dialog borrows the sign-in card's field, so the password sits after an empty 40px gap reserved for an icon that is not there (team (starter password dialog)) | Fixed. |
| D31 | medium | At phone width, most controls are 16-28px, below a 32px tap target, and nothing enlarges them on touch (phone, all screens) | Fixed. |
| D32 | medium | KPI tiles collapse two different ways on a phone: one per row at 154-175px tall on most screens, two-up at 108px on Finance (phone: overview, customers, loans vs liability) | Fixed. |
| D33 | medium | At phone width, the day-by-day chart's last two date labels print on top of each other (phone: forecast (and any day-by-day trendChart)) | Fixed. |
| D34 | low | On a phone, action rows keep text, priority pill and Track button in one line, squeezing the text into a 150px column with orphan words (phone: overview, seo, keywords, customers (recommended actions)) | Fixed. |
| D35 | low | The 'Add a skill' heading looks like a button, the saved-skill cards are ragged, and 'Show more' is centred under left-aligned text (skills) | Fixed. |

