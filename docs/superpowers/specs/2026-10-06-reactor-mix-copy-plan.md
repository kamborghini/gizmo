# Reactor copy plan: explanatory text, screen by screen

> Appendix to `2026-10-06-reactor-mix-design.md`. Made on 5 Oct 2026 against commit aa3623d, so its line numbers will drift as the build goes. Where it and the spec disagree, the spec wins. In particular, the Forecast wording Cameron approved is: "method" instead of "source"; ranges Today, Week, Month, 3 months, 12 months, Months ahead; statuses Safely ahead, Likely ahead, Likely behind. The "brief" it refers to is the text rules in section 7 of the spec.

Audit of every piece of explanation a user sees by default in `static/index.html` (branch design/brand-foundation, 5 Oct 2026), against the brief’s Text rules: one short line under a page title at most, no description under a card unless it is a warning, explanations behind an info button beside the title or in the Guide, empty states of one line of 8 words or fewer with their action. Nothing in the repo was changed.

## Totals

| Scope | Items | Words now | Words left on screen by default | Drop | Shorten | Popover | Keep |
|---|--:|--:|--:|--:|--:|--:|--:|
| Screens, default view (setup excluded) | 211 | 3400 | 965 | 37 | 98 | 35 | 41 |
| Admin setup cards and steps | 26 | 609 | 85 | 0 | 5 | 18 | 3 |
| Sign-in and dialogs | 55 | 1248 | 503 | 1 | 32 | 11 | 11 |
| **All** | **292** | **5257** | **1553** | **38** | **135** | **64** | **55** |

On the screens alone, explanation falls from 3400 words to 965 (72% less). Every word moved to a popover is kept, word for word, behind the info button or in the Guide; nothing is lost.

By kind:

| Kind | Items | Words now | Words left | Drop | Shorten | Popover | Keep |
|---|--:|--:|--:|--:|--:|--:|--:|
| intro | 32 | 752 | 231 | 4 | 27 | 0 | 1 |
| card description | 57 | 1053 | 67 | 26 | 7 | 23 | 1 |
| sub-line | 8 | 214 | 40 | 0 | 6 | 2 | 0 |
| empty state | 53 | 618 | 293 | 0 | 33 | 0 | 20 |
| note | 37 | 442 | 157 | 5 | 22 | 5 | 5 |
| help | 47 | 1098 | 293 | 3 | 23 | 16 | 5 |
| notice | 25 | 363 | 332 | 0 | 5 | 0 | 20 |
| setup | 33 | 717 | 140 | 0 | 12 | 18 | 3 |

## What each screen keeps under its title

For the mockups: the one line left under each page title, and the info buttons that carry what moved.

| Screen | Line under the title after the plan | Info buttons (what they hold) |
|---|---|---|
| Overview | none (the AI summary moves to a Summary card; before the first run the gate says "Live figures and an AI summary of the store.") | Average Google position |
| SEO | none once run; the gate line before | Average position |
| Keywords | none once run; the gate line before | Paid search (how to link Google Ads); Search data (the two sources) |
| Products | "Open a product for its optimisation plan." | none |
| Customers | none once run; the gate line before | none |
| Liability | "What customers owe on unpaid orders." | Page title: the unpaid tags and the terms rule |
| Reconciliation | "Checks Shopify, Xero and the inbox agree. Read only." | Connect the accounts mailbox; Connect Xero (setup, or a Guide link) |
| Forecast | "Cash taken and expected, against the cash flow plan." | Expected this month (how certain); Compare sources; Why the figure is what it is (method) |
| Xero sync | "Shopify orders, refunds and customers, sent into Xero." | Review and send; each of the three tiles; Settings (credentials stay on the service); the link card |
| Production Manager | none | Unprocessed and To make queue titles |
| Size list | "The glass size the bench cuts for every fixture." | Page title: a ruling made here wins over the sheet |
| CRM | "Deals, activities and contacts for the sales desk." | Page title: the amber and red key; Leads (what a lead is); How far deals get |
| Loan units | "Projectors out on loan, and for how long." | none |
| Inbox | "The shared mailbox, with an owner on every email." | Page title: amber then red; Connect the shared mailbox (setup) |
| Files | "The office file server, from anywhere." | Files (dragging to upload and move); Trash (30 days); Connect the storage (setup) |
| Team | "Who can sign in, and what everyone has done." | People (accounts and tab access); Recent sessions (export); Activity (how much is kept) |
| Memory | "What Reactor remembers with every answer." | Store knowledge; Notes; Tracked changes |
| Skills | "Playbooks Reactor follows in chat, reports and email drafts." | Your skills; How they are used (and its two advice lines) |
| Chat | none; the empty chat says "Ask about products, orders, customers and stock." | Send button tooltip: Enter and Shift+Enter |
| Guide | none (the tabs say it) | Requests (admin view) |
| Design | none | Colours; Type; Shape and space; Buttons; Tabs and choices; Tables; Fields |

**How to read the tables.** Words are counted as tokens with a letter or digit, on the text as it renders (sample figures from the local copy where the text carries data). *Left* is what stays on screen by default: 0 for drop; the new line for shorten; for popover, 0 or the one short line named in *New text or line that stays* (used where a warning or consequence must stay visible). Rows marked *varies* are not counted. Line numbers point at `static/index.html`.

**Rules applied.** Shortened text is 10 words or fewer (8 or fewer for an empty state), British English, no em or en dashes and no spaced hyphen used as one, and never names a setting, an environment variable, the host or the repo. Anything that protects someone from a mistake (a cost before an AI run, a warning before an irreversible step, a security note) is kept or put behind a popover, never dropped; where it is shortened, the warning itself survives in the new line.

**Not counted.** The AI summary that fills the intro slot on Overview, SEO, Keywords, Customers and a product plan once a report has run (40 to 80 words of grey prose, data rather than explanation): it should move out of the header into a Summary card at the top of the page, so the header keeps its one line. Loading lines ("Reading up to two years of unpaid orders...") are transient. Confirmation windows before destructive actions are warnings and stay as they are. Guide article text is documentation and out of scope; only its header and card chrome are here.

**Sources.** grep over the builders (`card-desc`, `card-sub`, `empty`, `-empty`, `note`, `hint`, `field-help`, `setting-sub`, `.ov-hero p`, run gates, setup steps), read in context; and a pass over the local copy at :8920 with `directions/copytext.js`, which visits every view and each of its tabs at 1440 and records the visible text. The local copy has no AI runs, no Xero, mailbox or storage connected and empty queues, so data states (Liability with debts, Xero sync linked, Inbox connected, Files connected) were read from the code.

## Overview

8 items, 91 words now, 34 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Compute live KPIs and an AI executive summary from your latest orders, customers and traffic. | 15 | **shorten** | Live figures and an AI summary of the store. | 9 | Run gate (before the first run); line 9203. |
| 2 | note | Uses AI credits only when you run it. | 8 | **keep** |  | 8 | Run gate. Cost warning, already short; line 9203. |
| 3 | intro | Here’s how your store is doing. | 6 | **drop** |  | 0 | Fallback when the AI summary is missing; says nothing. Lines 9226, 9351. |
| 4 | notice | 3 notable changes since the last scheduled refresh | 8 | **shorten** | 3 changes since the last refresh | 6 | Alerts banner head; line 9269. |
| 5 | card description | Revenue, orders and average order value by the sector each customer trades in. | 13 | **drop** |  | 0 | Sales by sector: the table columns say it; line 9388. |
| 6 | empty state | Trends populate after you run the overview, as orders accrue and Google is connected. Up to 24 months of history are shown here. | 23 | **shorten** | No trends yet. Connect Google to add traffic. | 8 | Performance over time; line 8361. Add a Connect action. |
| 7 | note | Lower is better. Position 1 is the top of search results. | 11 | **popover** |  | 0 | Average Google position chart; line 8407. Also on SEO. |
| 8 | note | last 24 months, whatever the range above | 7 | **shorten** | last 24 months | 3 | Traffic by channel period; line 8399. |

## SEO

6 items, 76 words now, 34 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Crawl your storefront and fuse Search Console, Analytics and Shopify sales into a money-ranked plan. | 15 | **shorten** | Crawl the store and rank fixes by revenue. | 8 | Run gate; line 9208. |
| 2 | note | Uses AI credits only when you run it. Can take up to a minute. | 14 | **shorten** | Uses AI credits. Takes up to a minute. | 8 | Run gate. Cost warning kept; line 9208. |
| 3 | intro | How your store performs across search, traffic and sales, and where to grow revenue. | 14 | **shorten** | Search, traffic and sales, and where to grow. | 8 | Fallback when no AI summary; lines 9426, 9442. |
| 4 | note | out of 100, optimisation health score | 6 | **shorten** | out of 100 | 3 | Score block; the card is already titled; line 9460. |
| 5 | empty state | Connect Google Search Console to chart search trends. Google provides up to 16 months of history. | 16 | **shorten** | Connect Search Console to see search trends. | 7 | Line 8427. |
| 6 | note | Lower is better. Position 1 is the top of search results. | 11 | **popover** |  | 0 | Average position chart; line 8436. |

## Keywords

10 items, 183 words now, 45 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Pull the keywords you rank for from Search Console and your paid spend, CPC and ROAS from Google Ads (via GA4), then get a money-ranked ... | 38 | **shorten** | Your keywords and ad spend, with a ranked plan. | 9 | Run gate; line 9501. |
| 2 | note | Uses AI credits only when you run it. Reads Search Console and GA4. | 13 | **shorten** | Uses AI credits. Reads Search Console and Analytics. | 8 | Run gate. Cost warning kept; line 9502. |
| 3 | intro | Your ranking keywords, paid performance, and where to win more profitable search traffic. | 13 | **shorten** | Keywords, paid search, and where to win traffic. | 8 | Fallback when no AI summary; lines 9515, 9635. |
| 4 | card description | Paste any public page (a competitor, a blog post) to extract the keywords and topics it targets, with ideas to compete. | 21 | **drop** |  | 0 | Scan a URL for keywords; put "A competitor or blog post address" in the field placeholder. Line 9609. |
| 5 | card description | Two Google sources fill the rest of this page. | 9 | **drop** |  | 0 | Search data is not connected yet; line 9656. |
| 6 | setup | Google Search Console, for the keywords you rank for and the clicks they bring. | 14 | **popover** |  | 0 | Step list; to the Guide. Line 9662. |
| 7 | setup | Google Ads, linked to your GA4 property (GA4 Admin, then Product links, then Google Ads links), for your spend, cost per click, conversions and ROAS. | 25 | **popover** |  | 0 | Step list; to the Guide. Line 9663. |
| 8 | empty state | No paid search data yet. Link Google Ads to your GA4 property (GA4 Admin, then Product links, then Google Ads links), and your spend, CPC, ... | 31 | **shorten** | No paid search data yet. | 5 | The linking steps go behind the info button; line 9546. |
| 9 | empty state | Connect Google Search Console to see the keywords you rank for. | 11 | **shorten** | Connect Search Console to see your keywords. | 7 | Line 9670. |
| 10 | empty state | No Search Console queries in this range yet. | 8 | **keep** |  | 8 | Already 8 words; line 9670. |

## Products

9 items, 113 words now, 45 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Load your catalogue with up to 24 months of sales so you can filter, sort, compare periods and export. | 19 | **shorten** | Your catalogue with up to 24 months of sales. | 9 | Run gate; line 9213. |
| 2 | note | Pulls live Shopify data. No AI credits used. | 8 | **drop** |  | 0 | Run gate; nothing to protect against. Line 9213. |
| 3 | intro | Filter, sort and compare your catalogue by revenue, sales, stock and more. Open a product for a full optimisation plan. | 20 | **shorten** | Open a product for its optimisation plan. | 7 | The first sentence lists the toolbar; line 10151. |
| 4 | card description | The six that earned most, last 12 months. | 8 | **drop** |  | 0 | Top products by revenue: the title and period chooser say it; line 10250. |
| 5 | empty state | Fewer than two of these products earned anything (last 12 months), so there is nothing to rank. | 17 | **shorten** | Nothing to rank for this period. | 6 | Line 10251. |
| 6 | note | Viewing 300 of 1,240 products. The first 300 are drawn: search or filter to reach the rest | 17 | **shorten** | Showing 300 of 1,240. Search or filter for more. | 9 | Table foot; line 10234. |
| 7 | note | The catalogue is larger than one read carries, so some products are not listed | 14 | **shorten** | Some products are missing: the catalogue is too large. | 9 | Warning about missing rows, kept; line 10236. |
| 8 | empty state | No products match these filters. | 5 | **keep** |  | 5 | Line 10261. |
| 9 | intro | The plan for this product. | 5 | **drop** |  | 0 | Product plan fallback when no AI summary; line 10317. |

## Customers

9 items, 114 words now, 60 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Analyse all customers and compare your sectors by retention, lifetime value and revenue, with a money-ranked plan. | 17 | **shorten** | Customers and sectors by retention, value and revenue. | 8 | Run gate, all customers; line 9724. |
| 2 | intro | Analyse the Events sector on its own: retention, lifetime value, segments, and a money-ranked plan for these customers. | 18 | **shorten** | The Events sector on its own, with a ranked plan. | 10 | Run gate, one sector; line 9725. |
| 3 | note | Uses AI credits only when you run it. Reads your Shopify customers and orders. | 14 | **shorten** | Uses AI credits. Reads Shopify customers and orders. | 8 | Run gate. Cost warning kept; line 9728. |
| 4 | intro | Who your best customers are, how well you retain them, and where to grow lifetime value. | 16 | **shorten** | Best customers, retention, and where to grow value. | 8 | Fallback when no AI summary; lines 9848, 9924. |
| 5 | intro | Retention and lifetime value for your Events customers. | 8 | **keep** |  | 8 | Sector fallback, 8 words; line 9848. |
| 6 | card description | From your orders and customer list. No AI credits used. | 10 | **drop** |  | 0 | Trade radar; line 9784. |
| 7 | sub-line | Nobody with a reorder rhythm is overdue right now. | 9 | **shorten** | No repeat accounts overdue. | 4 | Trade radar, empty list; line 9799. |
| 8 | sub-line | Every likely-trade customer already carries a sector tag. | 8 | **shorten** | Every trade customer is tagged. | 5 | Trade radar, empty list; line 9824. |
| 9 | sub-line | Tag these in Shopify and the sector analytics will see the whole trade side. | 14 | **shorten** | Tag these in Shopify to count them as trade. | 9 | Instruction at the moment of action; line 9826. |

## Liability

6 items, 106 words now, 36 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Credit extended to customers, from orders tagged "Purchase order unpaid", "Bank transfer unpaid", "Procurement unpaid". Terms come from the order itself, then a Net tag ... | 35 | **shorten** | What customers owe on unpaid orders. | 6 | Line 11967. The tag list and the terms rule go behind the info button. The loading version (line 11853, 8 words) takes the same line. |
| 2 | card description | Every unpaid order by how late it is, as a share of £12,430 outstanding. | 14 | **drop** |  | 0 | Aged debt: the bar and its legend show it; line 12056. |
| 3 | notice | Paid but still tagged. 2 settled orders still carry an unpaid tag and are left out of the totals. Untag them in Shopify. | 23 | **keep** |  | 23 | Warning; line 12066. |
| 4 | card description | Open one to see the orders behind the figure, when each is due, and what has been paid against it. | 20 | **drop** |  | 0 | Customers owing: rows that open say so with a chevron; line 12172. |
| 5 | empty state | No orders currently carry an unpaid tag. Nothing is owed. | 10 | **shorten** | Nothing is owed. | 3 | Lines 12169 and 12203 (same sentence twice). |
| 6 | empty state | Nothing matches these filters. | 4 | **keep** |  | 4 | Line 12202. |

## Reconciliation

15 items, 295 words now, 62 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Checks that Shopify, Xero and the inbox agree: every sale in the books, every payout in the bank, every document accounted for. It reads all ... | 29 | **shorten** | Checks Shopify, Xero and the inbox agree. Read only. | 9 | Line 16695. "Read only" is the safety point, kept. |
| 2 | notice | Notes from the last sweep, 4 Oct (then the service’s notes as a list) | 14 | **keep** |  | 14 | Status from the last run; line 16795. |
| 3 | setup | Reconciliation reads remittances, supplier invoices and statements from the accounts mailbox. That is a different Google account from the one behind the Inbox tab, and ... | 30 | **popover** |  | 0 | Connect the accounts mailbox; line 16813. |
| 4 | setup | Add this callback URL to your Google OAuth client, beside the one the Inbox tab already uses (APIs and Services, Credentials, your OAuth client, Authorised ... | 43 | **popover** |  | 0 | Step 1; to the Guide, with the address and its Copy button kept beside the step. Line 16827. |
| 5 | setup | Type the accounts mailbox address and connect it. The address is required: it is what makes Google open the right account rather than the one ... | 31 | **shorten** | Type the accounts mailbox address, then connect. | 7 | Step 2; line 16855. The why goes behind the info button. |
| 6 | setup | If a different mailbox is connected anyway, nothing is saved and the page says which one it got, so try again in a private window. | 25 | **popover** |  | 0 | Line 16908. |
| 7 | setup | Ask the master account to connect it. | 7 | **keep** |  | 7 | Non-admin; line 16911. |
| 8 | setup | A one-time setup of about five minutes. Xero is connected read-only: the app can read the books and has no way to change them. | 24 | **popover** | Read only: Reactor cannot change your books. | 7 | Connect Xero; security point stays as the line. Line 16920. |
| 9 | setup | Create a free app at developer.xero.com (My Apps, New app, Web app). | 12 | **popover** |  | 0 | Step 1; to the Guide. Line 16933. |
| 10 | setup | Set its redirect URI to exactly https://reactor.example/oauth/xero/callback. | 7 | **popover** |  | 0 | Step 2; to the Guide, the address and Copy stay. Line 16934. |
| 11 | setup | Put the Client ID and Client Secret into the Railway variables XERO_CLIENT_ID and XERO_CLIENT_SECRET (never anywhere else), then redeploy. The Connect button appears here once ... | 29 | **popover** |  | 0 | Step 3; names hosting and variables (copy rule). To the Guide. Line 16935. |
| 12 | setup | Sign in as the organisation and approve. | 7 | **keep** |  | 7 | Beside the Connect button; line 16982. |
| 13 | card description | Where Shopify, Xero and the inbox disagree. Open one to see both sides and say what it was. | 18 | **drop** |  | 0 | Discrepancies; line 17022. |
| 14 | empty state | Connect Xero above, then run the first sweep. | 8 | **keep** |  | 8 | 8 words; line 17048. |
| 15 | empty state | Nothing needs attention with these filters. That is the goal state. | 11 | **shorten** | Nothing needs attention. | 3 | Line 17047. |

## Forecast

19 items, 384 words now, 105 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | What the shop has taken, where the coming months are heading, and how that compares with the cash flow plan. Figures are cash in; what ... | 35 | **shorten** | Cash taken and expected, against the cash flow plan. | 9 | Line 15616. "A range, never a promise" moves into the range popover. |
| 2 | note | taken so far in Oct 2026, 1 of 31 days in | 11 | **shorten** | Oct 2026, day 1 of 31 | 6 | Under "Where I am now"; line 14957. |
| 3 | note | likely £41,327 to £66,054 · plan £37,566 | 6 | **keep** |  | 6 | Figures, not explanation; line 14967. |
| 4 | note | plan £286,687 | 2 | **keep** |  | 2 | Figure; line 14976. |
| 5 | note | How certain is that? Oct 2026 should land within about £12,364 either side of £53,691, 8 times out of 10. It is an expectation, not ... | 27 | **popover** |  | 0 | On the info button beside "Expected this month"; line 14988. |
| 6 | note | Expected £53,691 against a plan of £37,566, 42.9% ahead; even the bottom of the likely range clears it. | 18 | **shorten** | 42.9% ahead of plan; the whole range clears it. | 9 | Worth looking at, row 1; month and figures sit in their own columns. Line 14908. |
| 7 | note | Expected £45,044 against a plan of £35,860, 25.6% ahead; the plan is still inside the likely range. | 17 | **shorten** | 25.6% ahead; plan still inside the likely range. | 8 | Worth looking at, row 2; line 14908. |
| 8 | note | Source: Shopify orders and the nightly forecast · taken so far, then the rest of the month forecast | 17 | **shorten** | Source: Shopify and the nightly forecast | 6 | Chart head; the legend already tells taken from forecast. Line 15236. |
| 9 | card description | Each source forecasts a month, so they can be compared on a monthly range rather than day by day. | 19 | **popover** |  | 0 | Compare sources on the chart; line 15262. |
| 10 | sub-line | The figure for Oct 2026 is money already taken plus what the leading source expects for the days left. Nothing else is added to it. | 25 | **shorten** | Taken so far, plus expected for the days left. | 9 | Why the forecast is what it is: the one sentence of method; line 15041. |
| 11 | note | Already taken, 1 of 31 days in | 7 | **shorten** | Already taken | 2 | Split bar label; the day count is in the figure note. Line 15069. |
| 12 | note | Still expected over the rest of the month | 8 | **shorten** | Still expected | 2 | Split bar label; line 15070. |
| 13 | sub-line | The days left come from the source in use, Big orders counted apart. It splits each month into orders under £2,000 and big orders. The ... | 86 | **popover** |  | 0 | Method: line 15081 plus the source’s own description from the run. |
| 14 | setup | Set FORECAST_INGEST_TOKEN on Reactor and, with the same value, on the forecasting service; the service then posts here each night. The setup is in forecast/README.md. | 25 | **popover** |  | 0 | No forecast yet; names a variable and a file (copy rule). To the Guide. Line 14738. |
| 15 | setup | The hook is configured. The nightly service has not posted a run yet: it runs at 03:00 and needs the workbook below. | 22 | **shorten** | The first run lands after 03:00. | 6 | No forecast yet; line 14737. |
| 16 | empty state | No workbook uploaded yet. An admin uploads the cash flow workbook with the button above; the nightly run reads it. | 20 | **shorten** | No cash flow workbook yet. Upload one above. | 8 | Line 14743. |
| 17 | notice | The run on 1 Oct did not finish, so this page shows the run as of 30 Sep. | 18 | **keep** |  | 18 | Warning; line 14721. |
| 18 | empty state | Pick a start and an end date to draw that range. | 11 | **shorten** | Pick a start and an end date. | 7 | Custom range; line 15156. |
| 19 | empty state | Nothing to draw for that range yet. Pick another above. | 10 | **shorten** | Nothing to draw for this range yet. | 7 | Line 15162. |

## Xero sync

22 items, 402 words now, 84 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Sends Shopify orders into Xero as invoices, refunds as credit notes, and new customers as contacts. Nothing is written until a review has shown you ... | 30 | **shorten** | Shopify orders, refunds and customers, sent into Xero. | 8 | Line 13699. The Auto Run state already has its own tag in the Connection card; with Auto Run on, that tag carries the warning. |
| 2 | setup | Reactor is not linked to the Xero connector yet, so nothing can be reviewed or sent from here. | 18 | **shorten** | Not linked to the Xero connector yet. | 7 | Link the connector service; line 13720. |
| 3 | setup | In Railway, open this app’s service and its Variables. / Set the connector service’s address on Railway’s private network. Its private domain ends .railway.internal and ... | 58 | **popover** |  | 0 | Four steps naming hosting and variables (copy rule); to the Guide. Lines 13736 to 13741. |
| 4 | setup | An admin links it in Railway. | 6 | **shorten** | An admin needs to link this. | 6 | Non-admin; copy rule. Line 13744. |
| 5 | setup | The connector runs as its own service (shopify-xero-connector) with its own ledger and failsafes. Reactor only drives it: credentials stay on that service, and its ... | 30 | **popover** |  | 0 | Security note, kept behind the button; line 13747. |
| 6 | note | invoices, credit notes and contacts in Xero | 7 | **drop** |  | 0 | Under Synced; line 13773. |
| 7 | note | did not write; retry once the cause is fixed | 9 | **drop** |  | 0 | Under Failed; the quarantine card says what to do. Line 13774. |
| 8 | note | held back rather than written with bad data | 8 | **drop** |  | 0 | Under Quarantined; line 13775. |
| 9 | notice | Xero linked | 2 | **keep** |  | 2 | Connection status; show as a tag. Line 13785. |
| 10 | notice | Auto Run off. Nothing runs on its own. Orders go to Xero only when you send them. | 17 | **shorten** | Auto Run off. Orders go only when you send them. | 10 | Line 13823. |
| 11 | notice | Auto Run on. Checking for new orders every 10 minutes and sending them to Xero. | 15 | **keep** |  | 15 | Unattended writing into the accounts: warning. Line 13821. |
| 12 | sub-line | Nothing has run yet: no review and no send. | 9 | **shorten** | Nothing has run yet. | 4 | Line 13913. |
| 13 | notice | The last review, on 4 Oct, needs attention. A review writes nothing. | 12 | **keep** |  | 12 | Health box, warning; line 13893. |
| 14 | card description | A review is a dry run: the service maps every eligible order and writes nothing. Send does exactly what the review showed. | 22 | **popover** |  | 0 | Review and send; line 13937. |
| 15 | help | Check it, read what it would write, then send that order. One already sent is never sent twice. | 18 | **popover** |  | 0 | One order tile; the Check then Send buttons carry the sequence. Line 14183. |
| 16 | help | Tag the orders in Shopify, check the tag, read what each would write, then send. The tag stays on; an order already in Xero and ... | 31 | **popover** |  | 0 | Every order with a tag tile; line 14317. |
| 17 | help | A Shopify payout reaches the bank as one figure covering many orders. This adds a note to each Xero invoice saying which payout paid it, ... | 47 | **popover** |  | 0 | Which payout paid it tile; line 14326. |
| 18 | empty state | None yet. Run a review to see what would be sent. | 11 | **shorten** | No review yet. | 3 | Latest review; line 14064. |
| 19 | card description | How it behaves. Credentials are not on this form: they stay on the service, and the server will not accept them from here. | 23 | **popover** |  | 0 | Settings card; security note. Line 14453. |
| 20 | card description | Reviews and sends alike, newest first. | 6 | **drop** |  | 0 | Run history; line 14543. |
| 21 | card description | Held back rather than pushed with bad data. Fix the cause, then retry. | 13 | **shorten** | Held back for bad data. Fix the cause, then retry. | 10 | Quarantine card, a warning; line 14579. |
| 22 | empty state | The list is empty now. Refresh to update the count. | 10 | **shorten** | Empty now. Refresh to update the count. | 7 | Line 14598. |

## Production Manager

19 items, 296 words now, 104 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | The bench queue, from a new order through to a booked courier. Pick a queue below, then an order to work on. | 22 | **drop** |  | 0 | The queue tabs say it; lines 17795, 17944. |
| 2 | card description | New orders not yet released to the workbench. Press Ready to make when one should join the To make queue. | 20 | **popover** |  | 0 | Unprocessed; line 17937. |
| 3 | card description | Orders released to the bench (tagged "IP" in Shopify). Select one to preview its label, then print. | 17 | **popover** |  | 0 | To make; the tag rule is worth keeping once. Line 17938. |
| 4 | card description | Orders marked made and ready to ship. Select one to dispatch a courier. | 13 | **drop** |  | 0 | To ship; line 17936. |
| 5 | card description | Orders already dispatched. Select one to reprint its label or view tracking. | 12 | **drop** |  | 0 | Complete; line 17935. |
| 6 | card description | Booked to an address you pasted in, with no Shopify order behind them. Reprint a label or check a tracking number here. | 22 | **drop** |  | 0 | Custom shipments; line 17803. |
| 7 | card description | Opened from the order page. Refresh shows the full production list. | 11 | **shorten** | One order, opened from Shopify. Refresh for all. | 8 | Single-order view; line 18126. |
| 8 | empty state | Nothing is waiting. New orders tagged "Unprocessed" in Shopify will appear here for release. | 14 | **shorten** | Nothing waiting to be released. | 5 | Line 18158. |
| 9 | empty state | Nothing is on the bench. Release an order from Unprocessed, or tag one "IP" in Shopify and refresh. | 18 | **shorten** | Nothing on the bench. | 4 | Line 18159; action: Go to Unprocessed. |
| 10 | empty state | Nothing is ready to ship. Mark orders made in "To make" to move them here. | 15 | **shorten** | Nothing ready to ship. | 4 | Line 18157. |
| 11 | empty state | No orders have been dispatched yet. Dispatch one from the "To ship" queue. | 13 | **shorten** | Nothing dispatched yet. | 3 | Line 18156. |
| 12 | empty state | No shipments booked to a pasted address yet. Press New shipment to book one. | 14 | **shorten** | No custom shipments yet. | 4 | Line 17829; action: New shipment. |
| 13 | empty state | Nothing in this queue matches "Hartley". Clear the search, or check another queue tab. | 14 | **shorten** | Nothing in this queue matches “Hartley”. | 6 | Line 18165. |
| 14 | empty state | Every live order has been printed. | 6 | **keep** |  | 6 | Unprinted filter; line 18166. |
| 15 | empty state | Every live order is marked made. | 6 | **keep** |  | 6 | Not made filter; line 18166. |
| 16 | note | Only the first 250 open orders could be checked for a missing "IP" tag, and none of those is missing it. | 21 | **shorten** | First 250 open orders checked: none missing the tag. | 9 | Line 18105. |
| 17 | notice | Possibly missing from production. 3 paid orders have gobo items but no "IP" tag. | 14 | **keep** |  | 14 | Warning; line 17568. |
| 18 | note | Actual size preview: 4 x 4 in. Text shrunk to 80% so the whole order fits one label. | 18 | **shorten** | Actual size, 4 x 4 in, text at 80%. | 9 | Label preview; line 18311. |
| 19 | notice | This order does not fit on 4 x 4 in - some rows would be cut off the printed label. Choose a larger stock size ... | 26 | **keep** |  | 26 | Warning before a bad print. Replace the spaced hyphen with a colon (copy rule). Line 18318. |

## Size list

4 items, 69 words now, 26 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Every fixture on the size sheet with the glass it takes: the holder, the image, and the size the bench cuts. A ruling made in ... | 40 | **shorten** | The glass size the bench cuts for every fixture. | 9 | Line 16366. "A ruling made here wins over the sheet" goes behind the info button. |
| 2 | notice | Sheet updated 11 Sep · the copy that came with the app | 11 | **shorten** | Sheet updated 11 Sep · built-in copy | 6 | Header stamp; line 16370. |
| 3 | empty state | Nothing is cut at 25 mm, and no holder takes 25 mm glass. | 13 | **shorten** | Nothing is cut at 25 mm. | 6 | Size search with no hit; line 16433. |
| 4 | empty state | No model matches “mac 2000”. | 5 | **keep** |  | 5 | Line 16430. |

## CRM

23 items, 305 words now, 75 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Deals, activities and contacts for the sales desk. Every open deal should carry a next activity; cards wearing the amber warning are the ones with ... | 39 | **shorten** | Deals, activities and contacts for the sales desk. | 8 | Line 22744. The amber and red key goes behind the info button. |
| 2 | card description | A lead is an enquiry that is not yet a deal: it waits here so the pipeline holds only real, qualified work. Convert it when ... | 28 | **popover** |  | 0 | Leads; a definition. Line 24743. |
| 3 | empty state | The inbox is clear. | 4 | **keep** |  | 4 | Leads; line 24759. |
| 4 | card description | Everything the desk is working on. The board groups the open ones by stage; the list ranks them by what moved last. | 22 | **drop** |  | 0 | Deals; line 23072. |
| 5 | empty state | An empty pipeline is a fresh start. Add your first deal, convert an enquiry from the Leads inbox, or rename the stages to your own ... | 28 | **shorten** | No deals yet. | 3 | Deals onboarding (heading and paragraph); line 23218. Actions: Deal, Pipeline. |
| 6 | card description | The calls, emails and meetings the desk owes. Overdue first; ticking one off takes it out of the list and into Done. | 22 | **drop** |  | 0 | Activities; line 24091. |
| 7 | note | Showing the first 400 of 520. | 6 | **keep** |  | 6 | Truncation; line 24171. |
| 8 | card description | Everyone the desk deals with: their organisation, how to reach them, and how much is open. | 16 | **drop** |  | 0 | Contacts, people (organisations variant, 14 words, also drops); line 24233. |
| 9 | help | Tick rows to delete people together. | 6 | **drop** |  | 0 | The row checkboxes show it; line 24278. |
| 10 | empty state | Nobody here yet. | 3 | **keep** |  | 3 | Contacts; line 24261. |
| 11 | card description | What closed, summed into the month it was won. | 9 | **drop** |  | 0 | Insights, Won by month; line 25108. |
| 12 | card description | Open deals, in the month they are expected to land. | 10 | **drop** |  | 0 | Insights, Expected to close. |
| 13 | card description | How many deals have reached each stage. A win counts as every stage. | 13 | **popover** |  | 0 | Insights, How far deals get: a counting rule. |
| 14 | card description | The reason recorded when each deal was marked lost. | 9 | **drop** |  | 0 | Insights, Why deals are lost. |
| 15 | card description | What the desk actually got done, by kind. | 8 | **drop** |  | 0 | Insights, Activities completed. |
| 16 | empty state | Nothing won yet. This fills in as deals are marked won. | 11 | **shorten** | No deals won yet. | 4 | Insights. |
| 17 | empty state | No open deal has an expected close date from this month on. | 12 | **shorten** | No expected close dates ahead. | 5 | Insights. |
| 18 | empty state | No pipeline stages yet. This fills in once the pipeline has stages. | 12 | **shorten** | No pipeline stages yet. | 4 | Insights. |
| 19 | empty state | No deal has been marked lost yet. | 7 | **keep** |  | 7 | Insights; 7 words. |
| 20 | empty state | No activity was marked done in the last 30 days. | 10 | **shorten** | Nothing done in the last 30 days. | 7 | Insights. |
| 21 | note | 4 open deals have no expected close date, so they cannot be forecast. | 13 | **shorten** | 4 open deals have no close date. | 7 | Under Expected to close; line 25126. |
| 22 | note | no deals closed yet / no wins yet | 7 | **keep** |  | 7 | Figure notes that explain a 0% or None; line 25062. |
| 23 | setup | Reads your Pipedrive account and writes nothing, to either system. | 10 | **keep** |  | 10 | Moving from Pipedrive (opened on demand, master only); safety reassurance. Line 22778. |

## Loan units

9 items, 83 words now, 33 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | The projectors that go out to customers, where each one is, and how long it has been gone. | 18 | **shorten** | Projectors out on loan, and for how long. | 8 | Line 13519. |
| 2 | note | with customers / ready to go / nothing past its date | 9 | **drop** |  | 0 | Figure notes that repeat their labels (Out now, On the shelf, Overdue); line 13528. |
| 3 | card description | Longest out first. | 3 | **drop** |  | 0 | Out now: a sort order; show it on the column. Line 13539. |
| 4 | empty state | Nothing is out: no units are in the register yet. | 10 | **shorten** | Nothing is out. | 3 | Line 13546. |
| 5 | empty state | Everything is on the shelf. | 5 | **keep** |  | 5 | Line 13546. |
| 6 | card description | Every loan unit the shop owns. | 6 | **drop** |  | 0 | The register; repeats the title. Line 13584. |
| 7 | empty state | No units yet. Add the first projector to start tracking it. | 11 | **shorten** | No loan units yet. | 4 | Line 13595; action: Add unit. |
| 8 | card description | A loan with no due date turns amber once it has been out this long. | 15 | **shorten** | Turns amber after this many days without a due date. | 10 | Chasing; help at the moment of action beside the number. Line 13666. |
| 9 | note | no date set, worth a chase | 6 | **shorten** | No due date | 3 | Row status; an amber dot carries "worth a chase". Line 13561. |

## Inbox

13 items, 268 words now, 102 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | The shared mailbox with an owner on every email. Claim what you are dealing with, and reply from Gmail as usual. Unclaimed emails go amber, ... | 27 | **shorten** | The shared mailbox, with an owner on every email. | 9 | Line 25273. The amber and red rule goes behind the info button. |
| 2 | setup | Connect the mailbox whose email the team answers. Google will ask which account to use: choose the shared mailbox, not your own account. Whichever account ... | 48 | **popover** | Choose the shared mailbox, not your own account. | 8 | Connect the shared mailbox; the warning stays as the line. Line 25300. |
| 3 | setup | The server needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET set first, with the Gmail API enabled in the same Google Cloud project. | 19 | **popover** | Google sign-in needs setting up first. | 6 | Names variables (copy rule); steps to the Guide. Line 25304. |
| 4 | setup | First time? Two switches in Google. Do these in the Google project this app already uses, so nothing you have already set up changes. | 24 | **popover** |  | 0 | Heading and sub-line; to the Guide. Lines 25339 to 25344. |
| 5 | setup | Switch on the Gmail API. | 5 | **popover** |  | 0 | Step 1, with its link; to the Guide. Line 25348. |
| 6 | setup | Open your existing web client and add this address under Authorised redirect URIs. Keep the address that is already listed: add this one alongside it, ... | 33 | **popover** |  | 0 | Step 2; to the Guide, the address and Copy stay. Line 25352. |
| 7 | setup | Ask an admin to connect the shared mailbox. Once it is linked, every email shows up here with an owner. | 20 | **shorten** | An admin needs to connect the shared mailbox. | 8 | Non-admin; line 25369. |
| 8 | notice | Sync problem: (the error). The list below may be missing mail that arrived after the last sync, 2 hours ago. | 20 | **keep** |  | 20 | Warning; line 25383. |
| 9 | card description | Where each person is working, and how much they are carrying. | 11 | **drop** |  | 0 | Who is on today; line 25434. |
| 10 | help | 24 emails. Tick a few to claim or close them together. | 11 | **shorten** | 24 emails | 2 | Bulk bar; line 25553. |
| 11 | notice | 3 unread emails are not in this view. Show unread | 10 | **keep** |  | 10 | Says what the view hides; line 25699. |
| 12 | empty state | This inbox is clear. / You are not holding any email right now. / Nothing has been marked done yet. / Nothing open. The unread ... | 34 | **keep** |  | 34 | Six filter empty states, each 8 words or fewer; lines 25707 to 25776. |
| 13 | empty state | Every email has an owner. Good. | 6 | **shorten** | Every email has an owner. | 5 | Line 25710. |

## Files

12 items, 245 words now, 54 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | The office file server, reachable from anywhere. Drag files in to store them; click a picture or PDF to preview it right here, anything else ... | 40 | **shorten** | The office file server, from anywhere. | 6 | Line 27539. The 30-day trash rule stays on the Trash tab. |
| 2 | setup | Files keeps its storage in a Cloudflare R2 bucket: durable, priced in pennies, and the app signs every transfer so nothing is public. Three keys ... | 37 | **popover** | Storage is not set up yet. | 6 | Connect the storage; names hosting (copy rule). Line 27557. |
| 3 | notice | Storage answered with an error: (the error). Uploads may fail until the R2 keys in Railway are right. | 18 | **shorten** | Storage error: uploads may fail until it is fixed. | 9 | Warning kept; copy rule (hosting, key names). Line 27571. |
| 4 | card description | 12 files and 3 folders here. Drag files in to store them, or onto a folder to move them. | 19 | **shorten** | 12 files, 3 folders | 4 | Counts, better in the title; line 28044. |
| 5 | help | Drag files, or whole folders, anywhere on the list to upload them here. Drag a file onto a folder, or onto a step of the ... | 30 | **popover** |  | 0 | Line 28056; the Guide’s Files article already says it. |
| 6 | card description | Searching every folder for “invoice”. Clear the search to go back to browsing. | 13 | **shorten** | Results from every folder. | 4 | Line 28038. |
| 7 | help | Dragging files in needs a folder to land in: clear the search to upload here. | 15 | **shorten** | Clear the search to upload here. | 6 | Line 28056. |
| 8 | empty state | Nothing here yet. Drag files in, or press Upload. | 9 | **shorten** | No files here yet. | 4 | Line 28127; action: Upload. |
| 9 | empty state | No file matches that search. | 5 | **keep** |  | 5 | Line 28080. |
| 10 | card description | 2 files (4.1 MB) waiting here. Everything is emptied for good 30 days after it was deleted; put a file back to keep it, or ... | 32 | **popover** | Deleted for good after 30 days. | 6 | Trash; the consequence stays as the line. Line 27590. |
| 11 | card description | Nothing deleted in the last 30 days. Files deleted from the browser wait here for that long, so a mistake can be undone. | 23 | **drop** |  | 0 | Trash, empty: the list says "The trash is empty." straight under it. Line 27594. |
| 12 | empty state | The trash is empty. | 4 | **keep** |  | 4 | Line 27618. |

## Team

10 items, 191 words now, 50 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | The app's own accounts, and what everyone has been doing. Each person signs in with their own username and password; their actions are recorded under ... | 27 | **shorten** | Who can sign in, and what everyone has done. | 9 | Line 28633. |
| 2 | card description | Who can sign in, what each may open, and what they have been doing. | 14 | **drop** |  | 0 | People; repeats the intro. Line 28681. |
| 3 | sub-line | Accounts belong to the app, not Shopify. New accounts get a starter password shown once; everyone chooses their own on first sign-in. Tabs controls which ... | 42 | **popover** |  | 0 | People; security note. Line 28996. |
| 4 | empty state | Nobody is clocked in. | 4 | **keep** |  | 4 | Work, On the clock now; line 29026. |
| 5 | empty state | No part-time accounts yet. Set someone's role to Part-time and the clock appears for them the next time they open the app. | 22 | **shorten** | No part-time accounts yet. | 4 | Work, Hours per person; the how-to goes behind the info button. Line 29049. |
| 6 | card description | The export covers the chosen dates, or everything kept when left blank. Each row is one session: date, clock in, clock out, hours, actions, and ... | 30 | **popover** |  | 0 | Recent sessions; line 29078. |
| 7 | empty state | No completed sessions yet. | 4 | **keep** |  | 4 | Line 29082. |
| 8 | card description | Newest first. The feed shows the last 600 actions; the full ledger keeps 8,000 and is in every backup. | 19 | **popover** |  | 0 | Activity; a retention rule. Line 29120. |
| 9 | empty state | Nothing recorded for that view yet. | 6 | **keep** |  | 6 | Line 29127. |
| 10 | notice | This is shown once and never again. Pass it on privately; they must choose their own password the first time they sign in. | 23 | **keep** |  | 23 | Starter password window; security. Line 28652. |

## Memory

11 items, 195 words now, 41 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | What Reactor keeps in mind with every answer: what it learned from your website, and the notes it keeps from chat or that you add ... | 30 | **shorten** | What Reactor remembers with every answer. | 6 | Line 10934. |
| 2 | card description | Reactor can read your homepage, pages and blog and keep what it learns about the business. It reads it with every answer until you delete ... | 26 | **popover** |  | 0 | Store knowledge, not yet learned; line 10646. |
| 3 | card description | Learned on 3 Oct from 12 pages of your website. Reactor reads it with every answer. | 16 | **shorten** | Learned 3 Oct from 12 pages. | 6 | Store knowledge, learned; line 10642. |
| 4 | notice | Only an admin can change it. | 6 | **keep** |  | 6 | Permission, non-admins; a lock icon would say it too. Line 10647. |
| 5 | sub-line | Learning the store is an AI run: it reads up to 12 pages of your website once, and uses AI credits. | 21 | **shorten** | Uses AI credits. Reads up to 12 pages, once. | 9 | Cost warning kept; line 10670. |
| 6 | card description | What Reactor keeps from chat, and what you add here. It reads the newest 40 of each kind with every answer. Rules for how to ... | 29 | **popover** |  | 0 | Notes (the member version runs to about 50 words); line 10759. |
| 7 | empty state | No notes yet. Reactor keeps a note when something in a chat is worth remembering, and you can add one here. | 21 | **shorten** | No notes yet. | 3 | Line 10774; action: Add note. |
| 8 | empty state | No notes match. | 3 | **keep** |  | 3 | Line 10805. |
| 9 | card description | Actions you pressed Track on in an answer, measured by your headline figures from that day. | 16 | **popover** |  | 0 | Tracked changes (shown once something is tracked); line 10539. |
| 10 | note | not read with answers: older than the newest 40 of its kind | 12 | **shorten** | Not read with answers | 4 | Note row status, as a tag; line 10833. |
| 11 | note | Waiting for an admin to keep it, from Priya. Reactor does not read it yet | 15 | **shorten** | Waiting for an admin | 4 | Note row status, as a tag; line 10830. |

## Skills

7 items, 240 words now, 14 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Instructions and playbooks Reactor follows: a brand voice, a discount policy, how to answer a trade enquiry. Write one here or upload a Markdown file. ... | 49 | **shorten** | Playbooks Reactor follows in chat, reports and email drafts. | 9 | Line 11161. |
| 2 | card description | Rules and playbooks, each with a title and a note of when it applies. Drop Markdown files here to add them. | 21 | **popover** |  | 0 | Your skills; line 11223. |
| 3 | empty state | No skills yet. Write one, or upload a Markdown file. Ideas: a brand voice guide, a discounting policy, an SEO checklist, or how to answer ... | 28 | **shorten** | No skills yet. | 3 | Line 11254; actions: New skill, Upload. The member version (20 words) takes the same line. |
| 4 | card description | With each question Reactor reads in full the skills that fit it best, up to 24,000 characters in all, and any marked for every answer. ... | 81 | **popover** |  | 0 | How they are used; line 11192. |
| 5 | note | None yet: answers name the skills they follow from now on. | 11 | **shorten** | None yet | 2 | Followed most; line 11200. |
| 6 | note | A clear note of when each applies helps Reactor see where one fits, or pick it with Skills when you ask. | 21 | **popover** |  | 0 | Not followed yet, after the list of names; line 11202. |
| 7 | note | Having it read shows you what Reactor will do with each, and gives it a short version to use when a skill is too long ... | 29 | **popover** |  | 0 | Not read by Reactor, after the list of names; line 11204. |

## Chat

5 items, 45 words now, 18 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Ask about your products, orders, customers and stock. Reactor reads your live figures and answers with findings and next steps, following your skills where they ... | 26 | **shorten** | Ask about products, orders, customers and stock. | 7 | Empty chat; line 8663. |
| 2 | help | Enter to send · Shift+Enter for a new line | 8 | **popover** |  | 0 | Composer; belongs in the Send button’s tooltip. Static markup line 5171. |
| 3 | notice | Slower, and costs more. Kept for this conversation. | 8 | **keep** |  | 8 | Deep switch on; cost warning. Static markup line 5169. |
| 4 | notice | Answer footnotes: who answered when the usual model could not; not kept as a note; noted for an admin; marked done in Memory; these may ... | varies | **keep** |  | varies | Status after an answer, each with its action; lines 8557 to 8609. Not counted in words (varies). |
| 5 | empty state | No conversations yet. | 3 | **keep** |  | 3 | Sidebar; line 9146. |

## Guide

7 items, 119 words now, 42 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | How the desk runs, what changed in Reactor, and what the team has asked for. | 15 | **drop** |  | 0 | The tabs under it say exactly this; line 22024. |
| 2 | card description | Notes up to 1 Oct · build 4b39260 · running since 5 Oct | 11 | **keep** |  | 11 | What’s new, Release notes: data. Line 22338. |
| 3 | card description | Anything the app cannot do yet, or does awkwardly. Short and specific beats polished. An admin answers each one here. | 20 | **shorten** | Ask for what the app cannot do yet. | 8 | Requests, member view; line 22386. |
| 4 | card description | What the team has asked for. Set each one Planned, Shipped or Declined with a reply, and the person who asked sees it here. | 24 | **popover** |  | 0 | Requests, admin view; line 22385. |
| 5 | empty state | Nothing asked for yet. / No release notes yet. | 8 | **keep** |  | 8 | Lines 22394, 22342. |
| 6 | empty state | Nothing in the guide mentions "dispatch". Ask for a feature if something is missing. | 14 | **shorten** | Nothing in the guide mentions “dispatch”. | 6 | Guide search; line 22320. |
| 7 | help | What should the app do that it does not do yet, or what gets in the way? It goes on Guide, Requests, where an admin ... | 27 | **shorten** | What should the app do that it cannot yet? | 9 | Ask for a feature window; line 22506. |

## Design

11 items, 210 words now, 7 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | card description | Every colour in Reactor is one of these, read from the one list at the top of the page. A screen asks for a role, ... | 40 | **popover** |  | 0 | Colours; line 22140. |
| 2 | card description | Two typefaces and six ranks. Titles are Bricolage Grotesque, from one list kept with the colours; everything else is Inter, with figures that line up ... | 27 | **popover** |  | 0 | Type; update it if the new direction drops Bricolage. |
| 3 | card description | One corner for each role, and a spacing scale every distance comes from. Controls are 32 tall in forms and 28 in toolbars and card ... | 26 | **popover** |  | 0 | Shape and space. |
| 4 | card description | Every control has the same 6px corner and 14px text. One teal button on a screen, for the thing the screen is for. | 23 | **popover** |  | 0 | Buttons. |
| 5 | card description | Three ways to choose, each made by one piece of code, so they look and behave the same on every screen. | 21 | **popover** |  | 0 | Tabs and choices. |
| 6 | card description | The strip of headline figures at the top of a report. | 11 | **drop** |  | 0 | Figures; the sample shows it. |
| 7 | card description | Every list of rows: the card is its frame, rows divided by hairlines, figures to the right. | 17 | **popover** |  | 0 | Tables. |
| 8 | card description | Labels above, help under, and what is wrong said in words beside the field. | 14 | **popover** |  | 0 | Fields. |
| 9 | card description | What a screen says when there is nothing to show, when something failed, and when something happened. | 17 | **drop** |  | 0 | Messages; the samples show it. |
| 10 | empty state | Nothing to list yet. When there is, it shows here. | 10 | **shorten** | Nothing here yet. | 3 | The house sample empty state should model the new rule; line 22261. |
| 11 | help | Picked from a list. | 4 | **keep** |  | 4 | Sample field help; line 22255. |

## Shared: report pages

4 items, 29 words now, 11 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | help | Ask anything about the numbers and recommendations on this page. | 10 | **drop** |  | 0 | Page chat, empty thread; the field placeholder already says it. Line 9023. On Overview, SEO, Keywords, Customers. |
| 2 | help | Suggested questions from this report | 5 | **shorten** | Suggested questions | 2 | Page chat; line 9022. |
| 3 | note | Followed your skills Brand voice and Trade enquiries | 8 | **shorten** | Followed: Brand voice, Trade enquiries | 5 | A second line under every report title; make it a small tag row. Line 7563. |
| 4 | note | Source: Shopify orders · last 12 months | 6 | **shorten** | Shopify · last 12 months | 4 | Every chart head (about 14 charts across 5 pages); line 7890. |

## Sign-in

4 items, 86 words now, 36 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | intro | Your own account, not Shopify's. Ask an admin if you do not have one yet. | 15 | **shorten** | Your own account, not Shopify’s. No account? Ask an admin. | 10 | Line 28527. |
| 2 | intro | Type the six-digit code from your authenticator app. If you have lost your phone, one of your recovery codes works here too. | 22 | **shorten** | Code from your authenticator app, or a recovery code. | 9 | Two-step screen; the recovery route stays. Line 28423. |
| 3 | intro | The app keeps its own accounts. Create the master admin account first: it controls everything, including the other accounts. You need the one-time setup code ... | 30 | **shorten** | Create the master admin account. You need the setup code. | 10 | First run only; line 28472. |
| 4 | intro | The starter password was only for getting in. Set your own before carrying on; nobody else ever sees it. | 19 | **shorten** | Set your own password before carrying on. | 7 | Line 28497. |

## Settings window

15 items, 276 words now, 129 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | help | Saved to your store and applied to every chat and every report as authoritative context. | 15 | **shorten** | Reactor reads this with every chat and report. | 8 | Store profile; static markup. |
| 2 | help | A code from your phone as well as your password. | 10 | **keep** |  | 10 | Two-step sign-in. |
| 3 | help | Put on the end of email you send from the Inbox, above the shop footer. Up to four lines: your name, and whatever you want ... | 27 | **shorten** | Ends every email you send from the Inbox. | 8 | Your sign-off. |
| 4 | notice | An admin sets the store profile and the preferences below. | 10 | **keep** |  | 10 | Members only. |
| 5 | help | Show low-stock figures and advice. Turn off for unlimited stock. / Prefer short, skimmable answers. / Always include actions and opportunities. / Call out risks ... | 28 | **keep** |  | 28 | Four preference lines, each 10 words or fewer. |
| 6 | help | Re-run your audits on a schedule so they stay fresh, and flag big changes as alerts. Off by default; uses AI credits on each run. | 25 | **shorten** | Re-run audits on a schedule. Uses AI credits each run. | 10 | Auto-refresh; cost warning kept. |
| 7 | help | How often to refresh and check for notable changes. | 9 | **drop** |  | 0 | Frequency; the choices say it. |
| 8 | help | When you erase a customer in Shopify, Shopify asks Reactor to erase what it holds about them too. Each request waits here for an admin ... | 44 | **popover** |  | 0 | Privacy requests; line 30065. |
| 9 | setup | Not encrypted. The refresh tokens and sign-in code secrets are stored in plain text. Set TOKEN_ENCRYPTION_KEY in Railway. | 18 | **shorten** | Not encrypted: secrets are stored in plain text. | 8 | Connections, Secrets; security warning kept, the fix goes to the Guide. Line 29597. |
| 10 | setup | Not receiving order events yet: the app does not know its own public address (set APP_URL in Railway). The app falls back to refreshing on ... | 31 | **shorten** | No live order events. Refreshing on a timer instead. | 9 | Connections, Live updates; line 29649. |
| 11 | setup | Set GOOGLE_OAUTH_CLIENT_ID / SECRET and enable the Gmail API to use the Inbox tab. | 13 | **shorten** | Not set up yet. Steps in the Guide. | 8 | Connections, Shared mailbox; line 29656. |
| 12 | setup | ZETA_URL and ZETA_SYNC_TOKEN are not set, so made glass is not booked against stock. | 14 | **shorten** | Not set up: made glass is not booked against stock. | 10 | Connections, Stock app; line 29661. |
| 13 | setup | Connected, but set GA4_PROPERTY_ID to pull traffic data. | 8 | **shorten** | Connected, but no Analytics property is chosen. | 7 | Connections, Google Analytics 4; line 29700. |
| 14 | setup | Connected, but set GSC_SITE_URL to pull search data. | 8 | **shorten** | Connected, but no Search Console site is chosen. | 8 | Connections, Search Console; line 29707. |
| 15 | setup | Only shown inside the app. Set RESEND_API_KEY and ALERT_EMAIL_TO on Railway to get them by email. | 16 | **shorten** | Only shown inside the app. | 5 | Connections, Email alerts; line 29732. |

## Other dialogs

34 items, 836 words now, 306 left by default (all of the screen's states summed, so never all on screen at once).

| # | Where | Current text | Words | Proposal | New text or line that stays | Left | Note |
|--:|---|---|--:|---|---|--:|---|
| 1 | notice | World Options is not connected yet. Add your API key to start dispatching couriers. | 14 | **shorten** | World Options is not connected yet. | 6 | Dispatch; the button under it says what to do. Line 19849. |
| 2 | help | Sizes in cm, weight in kg. Weigh the packed box: couriers re-weigh on collection and bill the difference. | 18 | **shorten** | Weigh the packed box: couriers re-weigh and bill it. | 9 | Dispatch and New shipment (same sentence twice); lines 19926, 20898. Billing warning kept. |
| 3 | help | What is in the parcel, for the customs paperwork. World Options generates the commercial invoice from these lines. | 18 | **shorten** | What is in the parcel, for customs. | 7 | Dispatch, international; line 20028. |
| 4 | notice | Courier warnings: no signature collected; goes to a pickup shop; EORI number missing; address incomplete; quote out of date; booked but window failed; could not ... | varies | **keep** |  | varies | Dispatch, each shown only when it applies; lines 19866 to 20550. Not counted in words (varies). |
| 5 | help | The value is declared to the courier. Insuring a parcel declared at zero is an argument the insurer wins, so it is worth getting right. | 25 | **shorten** | Declared to the courier. A zero value cannot be insured. | 10 | New shipment; warning kept. Line 20861. |
| 6 | help | Going outside the UK, so the courier needs to know what is in the parcel and what it is worth. This travels with the shipment. | 25 | **shorten** | Outside the UK: list what is in the parcel. | 9 | New shipment; line 21037. |
| 7 | help | What is coming today, and from whom, by World Options’ own collection reference from the booking. Their service cannot be asked what is scheduled, so ... | 37 | **popover** | Collections booked in their portal do not show. | 8 | Collections; the gap stays as the line. Line 20690. |
| 8 | help | From your World Options web service setup. The Meter Number is required; add the Key and Password if you were given them. | 22 | **shorten** | The Meter Number is required; Key and Password optional. | 9 | Shipping settings; line 21357. |
| 9 | help | Where parcels ship from. Left blank, your Shopify store address is used. | 12 | **shorten** | Left blank, your Shopify store address is used. | 8 | Shipping settings; line 21401. |
| 10 | help | Collection window: when the courier can pick up from you. Sent with every booking. | 14 | **shorten** | When the courier can collect. Sent with every booking. | 9 | Shipping settings; line 21419. |
| 11 | help | Tells the courier whether to send a driver for each booking or that pickup is already covered. Picking the wrong one can double-book collections. | 24 | **keep** |  | 24 | Shipping settings; warning. Line 21447. |
| 12 | help | What each printer is loaded with. Production labels are the gobo labels from the Production Manager; courier labels are the shipping labels that come back ... | 28 | **popover** |  | 0 | Shipping settings, label sizes; line 21456. |
| 13 | help | Used automatically when an order ships outside the UK. Your EORI number is required for exports; get one at gov.uk if you do not have ... | 26 | **shorten** | Required for exports. Get one at gov.uk. | 7 | Shipping settings, international; line 21488. |
| 14 | help | Ask the EU database whether a business customer’s EORI number is real before you put it on an export. Nothing here is saved: it is ... | 27 | **shorten** | Checks a customer’s EORI number. Nothing is saved. | 8 | Shipping settings; line 21527. |
| 15 | help | A collection is arranged with the parcel, so this is what each courier is asked for when you book with them. Set the ones you ... | 35 | **popover** |  | 0 | Shipping settings, collection by courier; line 21553. |
| 16 | help | The parcel sizes you offer when dispatching. Dimensions in cm, weight in kg. Tick one to have the dispatch panel open on it; leave them ... | 33 | **shorten** | Parcel sizes in cm and kg. Tick the default. | 9 | Shipping settings, boxes; line 21595. |
| 17 | help | This is the order note exactly as Shopify holds it, including the proposal link if there is one. The order tags are not editable here: ... | 46 | **popover** |  | 0 | Edit order; line 19754. |
| 18 | help | These sit on top of the size list and survive replacing it. Removing one puts the model back to whatever the sheet says. | 23 | **popover** |  | 0 | Size rules; a consequence. Line 18436. |
| 19 | help | Leave the customer blank and this size applies to every order. Fill it in and it applies only to that customer, with the general size ... | 30 | **shorten** | Leave the customer blank to apply it to every order. | 10 | Size rule; line 18537. |
| 20 | help | Items on this model stop counting towards size-list coverage, so it will not be reported again, and their labels print no size and no CHECK. ... | 32 | **popover** | Its labels print no size from now on. | 8 | Size rule, Not a gobo; consequence stays as the line. Line 18582. |
| 21 | help | A due date is optional. Without one this loan is never called late; it turns amber once it has been out longer than the chase ... | 26 | **shorten** | Optional. Without one, it turns amber at the chase limit. | 10 | Loan it out; line 13299. |
| 22 | help | Lost is an outcome, not a deletion: the deal keeps its history and the reason feeds the Insights view. | 19 | **shorten** | The deal keeps its history; the reason feeds Insights. | 9 | Mark lost; line 23634. |
| 23 | help | That was the last open activity on this deal. A deal without a next step goes quiet, so schedule the next one now, or close ... | 33 | **shorten** | That was the last open activity. Schedule the next one? | 10 | Follow-up activity; line 23965. |
| 24 | notice | Pick the duplicate. Its deals, activities and notes move onto this contact, its extra details fill any gaps, and the duplicate is removed. This cannot ... | 27 | **keep** |  | 27 | Merge contacts; irreversible. Line 24573. |
| 25 | help | Rename the stages to your own process. Probability weights the pipeline value; rotting turns a deal red after sitting untouched that many days. | 23 | **popover** |  | 0 | Pipeline stages; line 24913. |
| 26 | notice | Deleted deals sit here for 30 days, then go for good. | 11 | **keep** |  | 11 | Deals bin; consequence. Line 23164. |
| 27 | help | Filters act on email as it arrives. A conversation someone is already holding is never re-filed underneath them. The first filter that matches wins, so ... | 34 | **popover** |  | 0 | Inbox filters; line 26029. |
| 28 | help | The footer goes on the end of every email sent from here, under the sender’s own sign-off. Fill in the lines this shop wants on ... | 49 | **popover** |  | 0 | Inbox email settings; line 26128. |
| 29 | help | A folder is a Gmail label, so it appears down the side in Gmail like any other. Use a slash for a folder inside a ... | 26 | **shorten** | A folder is a Gmail label. Use / to nest. | 9 | Inbox filter form; line 26393. |
| 30 | help | Formatting, files and pictures go out as they look here, with your sign-off and the shop footer under them. | 19 | **shorten** | Sent as shown, with your sign-off and the footer. | 9 | Compose; line 26775. |
| 31 | notice | Read it before it goes anywhere. Claude leaves gaps like ____ where it would have had to guess at a price or a date: fill ... | 26 | **keep** |  | 26 | AI draft; warning. Line 26818. |
| 32 | help | Add this to an authenticator app, then type the six-digit code it shows to prove it works. It is not on until you do. | 24 | **keep** |  | 24 | Two-step setup; line 29965. |
| 33 | notice | Two-step sign-in is on. Keep these recovery codes somewhere safe - each one gets you in once if you lose your phone, and this is ... | 30 | **keep** |  | 30 | Security. Replace the spaced hyphen with a colon (copy rule). Line 29986. |
| 34 | help | Xero document window, five method notes: tax added by Xero; update could not be read; not paid out yet; this order in that payout; what ... | varies | **popover** |  | varies | Lines 12700 to 12790; about 100 words in all, shown one or two at a time. Not counted in words (varies). |


## Patterns

1. **Every page opens on a paragraph.** 19 of 20 page intros run past 10 words and 12 past 25 (Skills 49, Size list 40, Files 40, CRM 39, Liability 35, Forecast 35, Xero sync 30, Memory 30, Reconciliation 29, Inbox 27, Team 27, Chat 26); the average is 27 words. Several describe what the tabs right under them already say (Production Manager, Guide), and Team says “what everyone has been doing” in the intro and again in the People card under it.
2. **Card descriptions that restate the card title.** The register: “Every loan unit the shop owns”. Discrepancies: “Where Shopify, Xero and the inbox disagree”. Aged debt: “Every unpaid order by how late it is”. Top products by revenue: “The six that earned most”. Who is on today: “Where each person is working”. Why deals are lost: “The reason recorded when each deal was marked lost”. Won by month, Expected to close and Activities completed do the same. Of 57 card descriptions, 26 drop outright and 23 move behind an info button.
3. **Descriptions that narrate the interaction the screen already shows.** “Open one to see the orders behind the figure”, “Select one to preview its label, then print”, “Select one to dispatch a courier”, “Tick rows to delete people together”, “Tick a few to claim or close them together”, “Drag files in to store them”, “Pick a queue below, then an order to work on”. A chevron, a checkbox or a drop target says each of these.
4. **Descriptions that only state a sort order.** “Longest out first.”, “Newest first.”, “Overdue first”, “Reviews and sends alike, newest first.” The sort belongs on the column head.
5. **One idea said at two levels.** Files Trash: “Nothing deleted in the last 30 days...” as the description and “The trash is empty.” straight under it. Each Production Manager queue explains itself in the description and again in its empty state. Liability writes “No orders currently carry an unpaid tag. Nothing is owed.” in two places (lines 12169, 12203). Team, Memory and Reconciliation stack three layers: a description, a second paragraph (`card-sub`) and then steps or an empty sentence.
6. **Two-sentence empty states.** The first sentence says it is empty, the second explains the mechanics (“This fills in as deals are marked won.”, “Reactor keeps a note when something in a chat is worth remembering”, “Release an order from Unprocessed, or tag one IP in Shopify and refresh”). 33 of 53 empty states are cut to one line; the second sentence becomes the empty state’s button (Add note, New shipment, Upload, Go to Unprocessed).
7. **Definitions and methods written inline.** “A lead is an enquiry that is not yet a deal”, “A review is a dry run”, the Forecast method (86 words) and confidence sentence, How Skills are used (81 words), the payout tile (47 words). These are exactly what the info button is for: wanted once, then in the way.
8. **Status written as a sentence beside a tag that already says it.** The Auto Run tag plus “Nothing runs on its own. Orders go to Xero only when you send them.”; “no date set, worth a chase”; “Waiting for an admin to keep it ... Reactor does not read it yet”; “not read with answers: older than the newest 40 of its kind”; “Xero linked” in a description slot. Each should be a tag or a coloured dot.
9. **Figure notes that repeat their label, and labels written as sentences.** Loan units: Out now / “with customers”, On the shelf / “ready to go”, Overdue / “nothing past its date”. Xero sync: Synced / “invoices, credit notes and contacts in Xero”. Forecast labels read as prose (“Where I am expected to be”, “Still expected over the rest of the month”); the brief wants 2 to 4 words (Taken so far, Expected this month, The year lands at).
10. **Counts in the description slot instead of the title.** Products (“1,240 products”), Files (“12 files and 3 folders here...”), Size list (“211 makers · 22 rulings...”). The brief puts a count in the title or as a small number beside it.
11. **The run gates repeat one cost line.** Five report screens open on a centred description plus a note; “Uses AI credits only when you run it.” appears on four of them and “No AI credits used” twice (Products gate, Trade radar). One small cost tag beside the Run button would replace all six.
12. **Setup copy breaks the copy rules.** The host is named in 9 user-facing strings (Xero sync steps and its member line, Reconciliation’s Xero step 3, the Files card and its error, and three Settings connection lines), and 16 variable names reach the screen (XERO_CLIENT_ID, XERO_CLIENT_SECRET, CONNECTOR_URL, CONNECTOR_TOKEN, DASHBOARD_TOKEN, FORECAST_INGEST_TOKEN, GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, TOKEN_ENCRYPTION_KEY, APP_URL, GA4_PROPERTY_ID, GSC_SITE_URL, RESEND_API_KEY, ALERT_EMAIL_TO, ZETA_URL, ZETA_SYNC_TOKEN), plus forecast/README.md. Each connection wants one Guide article, linked from a one-line card; the card keeps any address to copy and its Copy button.
13. **A spaced hyphen used as a dash.** The label clip warning (“4 x 4 in - some rows would be cut off”, line 18319), the recovery codes (“somewhere safe - each one”, line 29987), the size rule window header (lines 18500, 18570), the printed label’s “DO NOT MAKE - CANCELLED” (line 18707) and the Pipedrive survey lines (22904, 22913).
14. **Hover-only help already exists and should become the info button.** Metric labels carry `title` help (`METRIC_HELP`, `.has-help`, line 5947), the Forecast table heads do too (`helpHead`, line 15585), and chips hide sentences in `title` (Booked, No terms). The code itself notes a tooltip is invisible on a tablet (line 18207), so the popover must open on tap and on keyboard. The sign-in “Forgot password?” disclosure (line 28554, hidden until pressed) is the model already in the app.
15. **The same sentence in two places.** “Sizes in cm, weight in kg. Weigh the packed box...” (Dispatch and New shipment); “Lower is better. Position 1 is the top of search results.” (Overview and SEO); “Uses AI credits only when you run it.” (four run gates). One string each, said once.
16. **The report header carries the report.** On Overview, SEO, Keywords, Customers and a product plan the AI summary (40 to 80 words) sits in the intro slot in grey, and “Followed your skills ...” adds a second line, so the header runs to 90 words before the first figure. Give the summary its own card, and the skills a small tag row.
17. **Sentences that open with the screen’s or card’s own subject.** “Files keeps its storage in...”, “Reconciliation reads remittances...”, “Reactor is not linked to...”, “Reactor can read your homepage...”, “A lead is...”. They are definitions, and definitions go to the Guide.
