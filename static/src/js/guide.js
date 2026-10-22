        /* ---------- view switching ---------- */

        // ---- Guide -----------------------------------------------------------
        // The desk manual. Deliberately static: no network, no AI, no run gate, so
        // it works when everything else is failing, which is exactly when it is
        // read. Printable, because the answer to "the booking failed" is needed at
        // the bench and not on a screen somebody is already fighting with.
        /* The desk manual. Each section and row can carry admin: true (shown
           to admins alone) or tab: 'view' (shown to whoever can open that
           page), so a member reads what they can do and an admin also reads
           the setup. It covered seven of the nineteen pages, told everyone to
           set up Cloudflare, and was wrong about the roles, the queues and the
           sign-in messages. '{dav}' is the file drive's address, built from
           wherever the app is running. */
        const GUIDE = [
            { id: 'first', h: 'Your first day', body: [
                ['Liability', 'Who owes money on account, how late it is, and a chasing email for each account.', { tab: 'liability' }],
                ['Forecast', 'Where the year is heading against the cash flow plan. An admin gives this page to a person; nobody has it by default.', { tab: 'forecast' }],
                ['Xero sync', 'Checks Shopify orders against Xero and sends what is missing. Given by an admin, like Forecast.', { tab: 'connector' }],
                ['Production Manager', 'The bench: orders from Unprocessed to Complete, labels, dispatch and the day sheets.', { tab: 'labels' }],
                ['Size list', 'Every gobo size the labels use, and the rulings made on top of the size sheet.', { tab: 'sizes' }],
                ['CRM', 'The sales desk: deals, leads, activities and contacts, with a next step on every open deal.', { tab: 'crm' }],
                ['Loan units', 'Which units are out, who has them, and when they are due back.', { tab: 'loans' }],
                ['Inbox', 'The shared mailbox, with an owner on every email.', { tab: 'mail' }],
                ['Files', 'The team’s shared files, which also open on a Mac as a network drive.', { tab: 'files' }],
                ['Team', 'Accounts, roles, who can open which pages, and who did what.', { admin: true }],
                ['Memory, Skills and Chat', 'Reactor, the assistant: what it keeps in mind, the playbooks it follows, and where you ask it things.', { tab: 'chat' }],
                ['Finding a page', 'Search at the top of every page (Command J) jumps to any page, and to anything in this guide.'],
            ]},
            { id: 'daily', h: 'The daily run', tab: 'labels', body: [
                ['1. Orders arrive tagged Unprocessed', 'They wait in the Unprocessed queue until you press Ready to make, which moves them into To make and changes the tag from Unprocessed to IP. Anything paid and open that has gobo items but no workflow tag at all shows in an amber strip on the To make queue with an Add to queue button.'],
                ['2. Print the production labels', 'Select an order to preview its label, then Print, or use Print all for the whole queue. An account order starts its 30-day payment terms when it is released.'],
                ['3. Make the gobos', 'The label carries the production size, the glass type and the artwork name. A boxed CHECK line means the size could not be worked out and needs a person to decide before making.'],
                ['4. Mark made', 'Press Mark made on the order. It moves to To ship, tagged PC. Nothing has been told to Shopify or the customer yet.'],
                ['5. Dispatch', 'In To ship, press Dispatch. Courier prices are usually already there, because the queue prices itself in the background. Pick a service, press Book, and the label prints.'],
                ['6. The customer is told', 'Shopify is told the order has shipped when it is both marked made and has a booked label, whichever happens last. That is when the shipping email with tracking goes out, and the order is tagged Complete.'],
                ['The five queues', 'Unprocessed, To make (tag IP), To ship (tag PC), Complete, and Custom shipments, which holds parcels booked to a pasted address with no Shopify order behind them.'],
            ]},
            { id: 'wrong', h: 'When something goes wrong', body: [
                ['A booking fails', 'The app already retried it once if the failure was clearly a World Options outage. Open Technical details under the error, press Copy, and send that to Cameron. It holds World Options’ exact words and what was sent, with the password and the customer’s details taken out. Nothing was charged unless a tracking number came back.', { tab: 'labels' }],
                ['A parcel must go now and the app will not book', 'Book it directly in the World Options portal, then mark the order made in the app. The rest of the flow works without the app having booked the label. Never let a fault hold up a collection.', { tab: 'labels' }],
                ['The courier label will not print', 'Press Reprint label. If it still will not, the label is also in the World Options portal under the tracking number.', { tab: 'labels' }],
                ['The production label will not print', 'Check the label printer is the one chosen in the print window and has label stock loaded, then press Print again. Printing twice is safe: a reprint does not release the order a second time.', { tab: 'labels' }],
                ['"Carrier not named" on a courier option', 'World Options did not say who runs that service. The price and the booking are still fine; its service code is shown so you can look it up.', { tab: 'labels' }],
                ['A customs line shows 0', 'The store prices custom gobos through the option dropdowns, so the base product price is zero. Type the real value in: it is remembered against that product and filled in next time. Customs treats goods valued at zero as suspect and can hold the parcel.', { tab: 'labels' }],
                ['An order is missing from a queue', 'Queues follow tags (see The five queues). Orders finished before a tag was renamed still carry Dispatched and still show. Check the order’s tags in Shopify. The search box takes an order number, a customer name or a tracking number. If you have just changed a tag in Shopify, press Refresh: switching queues reuses the last read of your orders so it stays instant.', { tab: 'labels' }],
                ['The app turns your sign-in down', 'It says why. "Check this computer’s clock" means the clock is out and Shopify’s sign-in looks expired to the app; set the clock to update itself. A sign-in that has run out needs signing in again. An account that has been switched off needs an admin. A starter password must be changed before anything else opens. Opened outside the Shopify admin, it asks you to open Reactor from inside it.'],
                ['Shopify or World Options is down', 'Ask an admin to look at Settings, Connections, which shows the live state of both and any errors from the last day. A Shopify outage lasting three hours raises an alert at the top of every page.'],
            ]},
            { id: 'dispatch', h: 'Dispatch, in detail', tab: 'labels', body: [
                ['Parcels', 'Pick a box preset, or type sizes in cm and weight in kg. Weigh the packed box: couriers weigh again on collection and bill the difference. Add a box sends several parcels on one booking.'],
                ['Prices', 'Every option shows the price including VAT, with the price before VAT beneath, cheapest first. Quoting is free. Only Book spends money, and it always asks first.'],
                ['NO SIGNATURE options', 'Shown only where the carrier really offers it, which is FedEx and DHL. Cheaper, but nobody signs for the parcel, so there is no proof the customer received it.'],
                ['Collection', 'The ready-from time is worked out when you book, so it is always a real future slot. Booking after your close time moves collection to the next working day.'],
                ['International', 'Needs your EORI number in Shipping settings. Each customs line takes a description, quantity, unit value, HS code and country of origin. Gobos default to their sale value and 9002.20.000; stocked items use their cost price and their own code. Projectors default to China, everything else to the UK. Everything can be changed before booking. We never pay the import on a customer’s behalf.'],
                ['Cancelling', 'Cancel shipment voids the booking at World Options, undoes the Shopify fulfilment if there was one, and puts the order back in its queue. Whether the charge is refunded is the courier’s rule, not ours.'],
            ]},
            { id: 'tools', h: 'The other tools', tab: 'labels', body: [
                ['Where they are', 'Under More, on the queue card of the Production Manager.'],
                ['Day sheet', 'An A4 cut list of everything not yet made: sizes, glass, quantities and tick boxes.'],
                ['Stock usage', 'Glass used by everything marked made on a chosen day, totalled by size and glass family.'],
                ['Dispatch manifest', 'Everything booked on a chosen day: courier, tracking, collection reference, cost and what the customer paid. Print it for the driver, or check it against the World Options invoice.'],
                ['Margins', 'What each dispatched order made: revenue and delivery before VAT and after discounts, less the cost of the goods and the courier. An order with a product that has no cost price in Shopify is listed as incomplete rather than counted. Labour is not included.'],
                ['Size check', 'Runs recent orders through the size list and reports models it could not match, so the list can be put right before those orders reach the bench. Resolve gives a model a production size (for one customer only if needed), says it is another name for a model already listed, or rules it out as not a gobo.'],
                ['Size rules', 'The rulings made with Resolve, listed so a wrong one can be undone. Changing sizes is a permission an admin gives each person on the Team page.'],
                ['Update size list', 'Replaces the gobo size list from a spreadsheet. The previous five versions are kept.', { admin: true }],
            ]},
            { id: 'sizes', h: 'The Size list', tab: 'sizes', body: [
                ['Finding a fixture', 'Type it the way an order names it: maker and model, with or without the punctuation, run together or apart. Shorthand works (ADJ, S4, 4 for Four), and so do the names the store sells a model under. A figure such as 66mm finds everything cut at that size. The best match comes first, and one wrong letter is put right, with a line saying so.'],
                ['What the label prints', 'Type a maker and a model and the line over the list gives the label’s own answer: the size an order with that name is cut at, or that its label will say CHECK and why. The row it picks is marked The label’s match.'],
                ['A model’s details', 'Click or tap a model for all the list knows about it: the size to cut and where it comes from, the holder and the image, the whole note, why it needs review, the other names it sells under and any size for one customer. Set size is there too, for anyone allowed to change sizes.'],
                ['From any page', 'The Search box in the top bar finds fixtures as well as pages. Choosing one opens the Size list at that model.'],
            ]},
            { id: 'inbox', h: 'The Inbox', tab: 'mail', body: [
                ['An owner on every email', 'Claim an email you are dealing with, or Assign it to someone. An email nobody has claimed turns amber after 4 hours and red after 8. The owner shows in Gmail as a label too, so it holds wherever you read the mail.'],
                ['Replying', 'Reply from Gmail as usual, or press Compose reply with Claude: it reads the thread, the customer’s orders and any of your skills that fit the email, and writes a draft for you to change. Nothing sends until you confirm the address it will go to.'],
                ['Filters', 'Standing rules shaped like Gmail’s: conditions on the sender, the subject or the words, then an action, such as handing the email to a person, sharing it round a group, closing it on arrival or filing it away.'],
                ['The order behind the email', 'Beside a message: the sender’s recent orders, whether each has been made and shipped, and the tracking, with a copy button.'],
            ]},
            { id: 'sales', h: 'The sales desk', body: [
                ['Deals', 'Every open deal should have a next step. A card shows whether its next activity is overdue, due today, not scheduled at all, or in the future, and finishing its last activity asks for the next one.', { tab: 'crm' }],
                ['Leads, activities and contacts', 'Leads wait to become deals; Activities lists calls, meetings and tasks by when they are due; Contacts holds people and organisations. Stages, labels and lost reasons are changed by admins alone.', { tab: 'crm' }],
                ['Pipedrive', 'An admin can import from Pipedrive. It previews what would change before it writes anything, and keeps a restore point.', { tab: 'crm', admin: true }],
                ['Loan units', 'Record who has a unit and when it is due back; it shows what is out and what is late, and takes a unit off the register when it goes for good.', { tab: 'loans' }],
            ]},
            { id: 'money', h: 'Money', body: [
                ['Liability', 'Unpaid account orders from the last two years, by customer and by how late they are. The terms come from Shopify’s own terms on the order first, then a Net tag, then the house default.', { tab: 'liability' }],
                ['Chasing', 'Open an account on Liability for its chasing email, written from the ledger: every unpaid order with its amount and days overdue. Change it, then send it.', { tab: 'liability' }],
                ['The finance pages', 'Forecast and Xero sync hold the company’s books, so nobody has them by default. An admin gives them to a person on the Team page.'],
            ]},
            { id: 'reports', h: 'AI credits and your pages', tab: 'chat', body: [
                ['What costs money', 'Chat, Learn my store on Memory, reading a skill, the Inbox’s reply drafts and, now and then, reading a pasted courier address ask the AI and use credits. Everything else reads Shopify and Reactor’s own records at no cost.'],
                ['Customise', 'The button in a page header lets you drag its cards into the order you want and hide the ones you do not use. The arrangement is kept on your own account.'],
                ['Printing a conversation', 'Download as PDF, in the top bar, prints the conversation you are looking at.'],
            ]},
            { id: 'assistant', h: 'Reactor, the assistant', tab: 'chat', body: [
                ['Chat', 'Ask anything about the store. Reactor reads your live figures (it can never change anything) and answers with findings and next steps. What Reactor read, under an answer, lists what it looked at. You can ask in another conversation while one is working, and Stop one that is taking too long.'],
                ['Track', 'On a recommended action, Track takes a snapshot of your headline figures and measures the change over the following weeks. Tracked changes are listed on Memory.'],
                ['Deep analysis', 'Reactor thinks for longer before it answers, in the conversation it is switched on in: slower, and it costs more. For questions that need several reports at once.'],
                ['Memory', 'The facts, decisions, preferences, learnings and follow-ups Reactor keeps from chat, and what it learned from the website. An admin can add or correct a note by hand. A rule for how Reactor should work belongs in Skills, and a note that reads like one is offered as a skill.'],
                ['Skills', 'Your playbooks: a brand voice, a discount policy, how to answer a trade enquiry. An admin writes one, or, from the master account, which can also save longer skills, upload Markdown files (a SKILL.md header gives the title and when it applies). Reactor picks the ones that fit each question, in chat, reports and email drafts, and says under each answer which it followed. Use in chat, or the Skills button beside the question box, applies one whatever the question; a short one can be applied to every answer.'],
                ['Having a skill read', 'Read and add, or Have Reactor read it (an admin\u2019s to run), is an AI run in which Reactor reads the skill closely and writes down when it applies, what it will do, and anything unclear. Check it before you rely on the skill, and read it again after you change the skill.'],
            ]},
            { id: 'never', h: 'What the app will not do', body: [
                ['Charge you twice', 'A booking is refused if the order already has a live label. If the result of a booking is unknown, the app says so and will not book again rather than risk a second charge.'],
                ['Tell the customer too early', 'Booking a label is preparation. Shopify is only told the order shipped once it is also marked made.'],
                ['Lose your work to a misclick', 'A window holding work you have typed closes only by its X, never on a click outside it or on Escape. Yes and no questions answer to Escape, which always means cancel.'],
                ['Delete on a stray Enter', 'A question that destroys something is red, opens with Cancel selected, and ignores Enter. It has to be clicked.'],
                ['Let the assistant change anything', 'Chat can only read your store. Tagging, fulfilling and booking are wired separately and cannot be reached by the assistant, whatever it is asked.'],
            ]},
            { id: 'files', h: 'Files', tab: 'files', body: [
                ['What it is', 'A shared file store for the whole team, reachable anywhere the app is. Uploads and downloads go straight between your browser and the storage, so big files move at full speed.'],
                ['Using it', 'Drag files, or whole folders, onto the list to upload them where you are; a dropped folder keeps its structure. Click a picture or PDF to preview it; other files download. Tick the box over a file’s icon to select several, then move or trash them together; Move works where dragging cannot, on a phone too. Uploading a name that already exists replaces it, with the old version kept in the trash. The trash keeps a file for 30 days.'],
                ['Files in Finder', 'On a Mac, the file store opens as a network drive: in Finder press Command K, enter {dav} and sign in with your own username and a drive password. Make the drive password with Finder drive on the Files page; your Reactor password does not open the drive. Everything lands in the same folders the Files page shows, and deleting there is the same 30-day trash. Use your own sign-in: the drive records who did what.'],
                ['If Finder keeps asking for the password', 'The drive takes the drive password made on the Files page, not your Reactor password. Changing your Reactor password, or an admin resetting it, removes the drive password, so make a new one. An admin can see why someone was refused on Team, Activity.'],
                ['Setting it up', 'Files needs a Cloudflare R2 storage account, connected once by whoever looks after the app’s hosting. Settings, Connections shows whether it is connected. It costs about 60p a month at 50 GB.', { admin: true }],
            ]},
            { id: 'team', h: 'The team', body: [
                ['Your own account', 'Reactor keeps its own accounts, a username and password each, separate from Shopify logins. Passwords are stored scrambled and shown to nobody, admins included.'],
                ['The four roles', 'The master admin controls everything, including the other accounts, and can never be demoted, switched off or deleted. Admins manage members and the day-to-day setup. Members do the work. Part-timers do the work and clock in and out.'],
                ['Who can open what', 'Each person has their own set of pages, chosen by an admin with Tabs on the Team page. Forecast and Xero sync are given by choice, never by default. Customer details, ticked by default, decides who may read customers’ names, contacts and order histories.'],
                ['Clocking in', 'Part-timers clock in and out from the account menu at the foot of the sidebar. The app keeps the times itself; a forgotten clock-out is corrected by an admin on Team, Work.'],
                ['Adding a person', 'Team, then New account: their name, a username and the role. The app makes a starter password and shows it once; pass it on privately. They must choose their own password when they first sign in.', { admin: true }],
                ['Forgotten passwords', 'Reset password on their row makes a new starter password, shown once. Their old password and open sign-ins stop working at once. Nobody can look up an existing password.', { admin: true }],
                ['Switching someone off', 'Switch off on their row signs them out that second. Delete (master only) removes the account for good; their history keeps their name.', { admin: true }],
                ['The activity ledger', 'Team, then Activity: who did what, newest first, by person or area. Sign-ins, failed sign-ins and every account change are recorded with the work itself.', { admin: true }],
                ['Two-step sign-in', 'Settings, Two-step sign-in asks for a code from a phone app as well as the password. An admin can reset it for someone who has lost their phone.', { admin: true }],
            ]},
            { id: 'house', h: 'Housekeeping', admin: true, body: [
                ['Backups', 'A snapshot is taken every week and the newest four are kept. They live in the same storage they protect, so download a copy now and then from Settings, Connections.'],
                ['Alerts', 'Settings, Connections shows what is healthy. Alerts and new feature requests are emailed only once alert email is set up; Connections says whether it is.'],
                ['Shipping settings', 'Origin address, box presets, collection window, insurance defaults, EORI and the World Options sign-in. The sign-in is write-only: the app never shows it again and never puts it in a backup.'],
            ]},
            { id: 'guide', h: 'What’s new and Requests', body: [
                ['What’s new', 'What changed in Reactor, newest first. A dot on Guide means there are notes you have not read.'],
                ['Asking for something', 'Ask for a feature, in the account menu at the foot of the sidebar or on Requests, says what the app should do that it does not. An admin answers each one on Requests, and you see the answer there.'],
            ]},
        ];
        const guideAdmin = () => !!teamMe && (teamMe.role === 'master' || teamMe.role === 'admin');
        /* The rows this person sees, section by section. */
        function guideFor() {
            const ok = (o) => !!o && (!o.admin || guideAdmin()) && (!o.tab || tabAllowed(o.tab));
            return GUIDE.filter(sec => ok(sec))
                .map(sec => Object.assign({}, sec, { body: sec.body.filter(([, , o]) => !o || ok(o)) }))
                .filter(sec => sec.body.length);
        }
        const davAddress = () => location.origin + '/dav';
        function guideText(d) { return String(d).replace('{dav}', davAddress()); }
        /* ==================================================================
           Guide, What's new and Requests share the one tab: they are the
           app talking ABOUT itself.
           ================================================================== */
        let guideSeg = 'guide', updCache = null, updAt = 0;
        /* Which paint of the Guide is the latest: a read for What's new that
           lands after the reader moved to another section must not clear it. */
        let guidePaintSeq = 0;
        const guideView = { q: '' };
        const reqView = { f: 'open', q: '', page: 1, size: 25, reply: null };
        const LS_SEEN_REL = 'sc_seen_release';   // the old per-browser date, read once for the first baseline
        /* Kept for three minutes: every switch between the three tabs fetched
           all the notes, requests and names again. */
        async function loadUpdates(force) {
            if (updCache && !force && Date.now() - updAt < 180000) return updCache;
            updCache = await api('/api/updates', {});
            updAt = Date.now();
            return updCache;
        }
        let guideUnread = { releases: 0, requests: 0 };
        function paintGuideDots() {
            const any = guideUnread.releases > 0 || guideUnread.requests > 0;
            const nav = $('nav-guide');
            if (nav) {
                const had = nav.querySelector('.nav-new-dot');
                const why = guideUnread.releases ? 'New release notes' : 'An answer on Requests';
                if (any && !had) { const dot = el('span', 'nav-new-dot'); dot.setAttribute('role', 'img'); nav.append(dot); }
                const dot = nav.querySelector('.nav-new-dot');
                if (dot) { if (!any) dot.remove(); else { dot.title = why; dot.setAttribute('aria-label', why); } }
            }
            /* A folded Workspace group carries the dot on its heading. */
            const grp = document.querySelector('.nav-group[data-group="workspace"]');
            if (grp) {
                const g = grp.querySelector('.nav-new-dot');
                const folded = grp.getAttribute('aria-expanded') !== 'true';
                if (any && folded && !g) { const dot = el('span', 'nav-new-dot'); dot.title = 'Something new on Guide'; dot.setAttribute('role', 'img'); dot.setAttribute('aria-label', 'Something new on Guide'); grp.insertBefore(dot, grp.querySelector('.nav-caret')); }
                else if ((!any || !folded) && g) g.remove();
            }
            document.querySelectorAll('#guide-content > .tabs > .tab').forEach(b => {
                const n = b.dataset.k === 'new' ? guideUnread.releases : b.dataset.k === 'requests' ? guideUnread.requests : 0;
                const d = b.querySelector('.tab-dot');
                if (n && !d) { const s = el('span', 'tab-dot'); s.append(el('span', 'sr-only', ', new')); b.append(s); }
                else if (!n && d) d.remove();
            });
        }
        async function updatesBadge() {
            /* A quiet dot on Guide when there are notes this person has not
               read, or an answer to their request. Never a number, never a
               toast: it is news, not work. */
            try {
                const u = await api('/api/updates', { op: 'version' });
                guideUnread = releaseBaseline(u.unread || {}, u.seen, (u.version || {}).releases || 0);
                paintGuideDots();
            } catch (e) { /* the dot is never worth an error */ }
        }
        /* Someone who never opened What's new on their account is not shown
           every release ever as new: the date this browser last read stands
           in, or else the last fortnight. */
        function releaseBaseline(unread, seen, total) {
            const out = { releases: unread.releases || 0, requests: unread.requests || 0 };
            if (seen && seen.releases != null) return out;
            let since = '';
            try { since = localStorage.getItem(LS_SEEN_REL) || ''; } catch (e) {}
            const rels = (updCache && updCache.releases) || null;
            if (rels) {
                const cut = since || new Date(Date.now() - 14 * 86400000).toISOString().slice(0, 10);
                out.releases = rels.filter(r => r.date > cut).length;
            } else out.releases = Math.min(out.releases, total ? 3 : 0);
            return out;
        }
        function markSeen(what) {
            const total = ((updCache || {}).releases || []).length;
            if (what === 'releases') guideUnread.releases = 0; else guideUnread.requests = 0;
            paintGuideDots();
            api('/api/updates', what === 'releases' ? { op: 'seen', releases: total } : { op: 'seen', requests: true })
                .then(r => { if (updCache && r && r.seen) updCache.seen = r.seen; })
                /* Not recorded: the dot is read again, so it shows what is true. */
                .catch(() => updatesBadge());
        }
        const GUIDE_SEGS = [['guide', 'Guide', 'How the desk runs, and what to do when something goes wrong.'],
            ['new', 'What’s new', 'What changed in Reactor, newest first.'],
            ['requests', 'Requests', 'Ask for what the app does not do yet, and see what happened to it.'],
            ['design', 'Design', 'Every colour and typeface in Reactor, and the shared parts its screens are built from, drawn by the same code the screens use.', 'admin']];
        /* Design is for admins: it is how the app is built, not how to use it. */
        const guideSegs = () => GUIDE_SEGS.filter(s => s[3] !== 'admin' || guideAdmin());
        function renderGuide() {
            const box = $('guide-content');
            box.dataset.built = '1';
            box.innerHTML = '';
            box.classList.toggle('no-intro', !firstPaint('guide'));
            /* One header for the whole set, the same on every tab, and no line:
               the tabs under it say what the Guide holds (copy plan, Guide #1).
               Print sits with the Guide's own search. */
            box.append(pageHead({ view: 'guide', title: 'Guide' }));
            /* A row of tabs that says which is showing, and keeps focus where
               it was pressed: the whole page was rebuilt and focus fell away. */
            if (!guideSegs().some(s => s[0] === guideSeg)) guideSeg = 'guide';
            box.append(tabStrip(guideSegs().map(([k, lab]) => [k, lab]), guideSeg, (k) => { guideSeg = k; paintGuideSeg(); }, { label: 'Guide sections' }));
            const host = el('div', 'guide-host'); host.id = 'guide-host'; box.append(host);
            paintGuideSeg();
        }
        function paintGuideSeg() {
            const box = $('guide-content'), host = $('guide-host');
            if (!host) { renderGuide(); return; }
            const meta = guideSegs().find(s => s[0] === guideSeg) || GUIDE_SEGS[0];
            if (meta[0] !== guideSeg) guideSeg = meta[0];
            box.querySelectorAll(':scope > .tabs > .tab').forEach(b => { const on = b.dataset.k === guideSeg; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
            paintGuideDots();
            host.replaceChildren();
            const ticket = ++guidePaintSeq;
            if (guideSeg === 'guide') { paintGuideBook(host); return; }
            if (guideSeg === 'design') { paintDesign(host); return; }
            const wait = el('div', 'thinking');
            wait.append(loader(), el('span', null, 'Reading…'));
            host.append(wait);
            loadUpdates().then(u => {
                if ($('guide-host') !== host || ticket !== guidePaintSeq) return;
                host.replaceChildren();
                if (guideSeg === 'new') paintReleases(host, u);
                else if (guideSeg === 'requests') paintRequests(host, u);
            }).catch(e => {
                if ($('guide-host') !== host || ticket !== guidePaintSeq) return;
                host.replaceChildren();
                host.append(loadFailure('The updates could not be read. ' + (e.message || ''), () => { updCache = null; paintGuideSeg(); }));
            });
        }
