// The states the suite measures. Every state names `seeded`, a text only the
// seed puts there (never in the page's own source; test_world.py proves a
// route carries it, or carries `proof` when the page composes the text), and
// the helpers below end each state by waiting for it, so an empty state is
// never measured by mistake. A state with no data of its own says why in
// `static`. Never click anything that writes: open tabs, rows and windows only.
const ACTIVE = '.view.active';
const WINDOW = '.modal-overlay.show .modal';

const page = (id, view, go, o) => ({
  id, view, kind: 'page', ...o,
  go: async (p, h) => { await go(p, h); if (o.seeded) await h.waitText(ACTIVE, o.seeded); },
});
const dialog = (id, view, before, opener, o) => ({
  id, view, kind: 'dialog', before, opener, ...o,
  go: async (p, h) => {
    await before(p, h);
    await p.evaluate(({ sel, text }) => {
      const e = [...document.querySelectorAll(sel)].filter(x => x.offsetParent || x.getClientRects().length)
        .find(x => !text || (x.innerText || x.getAttribute('aria-label') || '').trim().startsWith(text));
      if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
      e.setAttribute('data-suite-opener', '');
      e.click();
    }, opener);
    await p.waitForSelector(WINDOW);
    await h.waitText(WINDOW, o.seeded);
  },
});

/* The stock list, read and drawn, as the table or (workshop) the count cards.
   A phone opens on the count cards, a desk on the table. */
const stockList = async (p, h, workshop) => {
  await h.nav('stock'); await h.tab('inventory'); await h.waitText('.view.active', 'Clear Etch');
  if (workshop !== h.phone) await h.clickText('.view.active', 'Workshop mode');
};
/* A stock tab, read and drawn: its text from the seed is showing. */
const stockTab = (tab, text) => async (p, h) => { await h.nav('stock'); await h.tab(tab); await h.waitText(ACTIVE, text); };
const stockReorder = stockTab('reorder', 'Amber 21');
const stockSuppliers = stockTab('suppliers', 'orders@northbeam.example');
const stockActivity = stockTab('activity', 'INV-24');
const crmBefore = async (p, h) => { await h.nav('crm'); await p.waitForSelector('#crm-content .tabs'); };
const labelsBefore = async (p, h) => { await h.nav('labels'); await h.waitText('#labels-content', '#210388'); };

module.exports = [
  page('liability', 'liability', async (p, h) => { await h.nav('liability'); }, { seeded: 'Kestrel Logistics Ltd' }),
  page('forecast', 'forecast', async (p, h) => { await h.nav('forecast'); }, { seeded: 'Algorithm 2' }),
  page('connector', 'connector', async (p, h) => { await h.nav('connector'); }, { seeded: 'test-store.myshopify.com' }),
  page('labels', 'labels', labelsBefore, { seeded: 'Hartwell Events Ltd' }),
  // The open order shows the customer's history: 'Repeat customer ... previous #210351'.
  page('labels~make-open', 'labels', async (p, h) => { await labelsBefore(p, h); await h.click('#labels-content .lbl-qrow'); await p.waitForSelector('#labels-content .lbl-preview'); },
    { seeded: '#210351' }),
  page('labels~shipments', 'labels', async (p, h) => { await h.nav('labels'); await h.queue('shipments'); }, { seeded: 'Loan projector return label' }),
  page('sizes', 'sizes', async (p, h) => { await h.nav('sizes'); await p.waitForSelector('#sizes-content tr.sizes-row'); await h.settle(); },
    { static: "the Size list reads the repository's own sheet (data/gobo-sizes.csv), not the seed" }),
  page('crm~leads', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('leads'); }, { seeded: 'Rental stock enquiry' }),
  page('crm~activities', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('activities'); }, { seeded: 'Site visit for window throw' }),
  // 'Won by month' is the chart's own title and shows with no deals; a lost reason does not.
  page('crm~insights', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('insights'); }, { seeded: 'Too expensive' }),
  page('crm~contacts', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('contacts'); }, { seeded: 'Marcus Bell' }),
  page('loans', 'loans', async (p, h) => { await h.nav('loans'); }, { seeded: 'Quayside Exhibitions' }),
  // Never open a thread here: opening one marks it read, a Gmail write.
  page('mail', 'mail', async (p, h) => { await h.nav('mail'); }, { seeded: 'Artwork for the autumn tour gobos' }),
  page('files', 'files', async (p, h) => { await h.nav('files'); }, { seeded: 'price-list-2026.pdf' }),
  page('stock', 'stock', async (p, h) => { await h.nav('stock'); }, { seeded: 'Q4 2026' }),
  page('stock~overview', 'stock', async (p, h) => { await h.nav('stock'); }, { seeded: 'hold most of the idle money' }),
  page('stock~inventory', 'stock', async (p, h) => { await stockList(p, h, false); }, { seeded: 'Clear Etch' }),
  page('stock~inventory-flat', 'stock', async (p, h) => { await stockList(p, h, false); await h.clickText('.view.active', 'Flat'); },
    { seeded: 'Lens hood' }),
  page('stock~workshop', 'stock', async (p, h) => { await stockList(p, h, true); }, { seeded: 'Clear Etch' }),
  page('stock~reorder', 'stock', stockReorder, { seeded: 'LED80 White' }),
  page('stock~reorder-levels', 'stock', async (p, h) => { await stockReorder(p, h); await h.clickText(ACTIVE, 'Set reorder levels from usage'); },
    { seeded: 'Lens hood' }),
  page('stock~suppliers', 'stock', stockSuppliers, { seeded: 'Brightway Lighting' }),
  page('stock~trends', 'stock', stockTab('trends', 'Mains adaptor 24V'), { seeded: 'Mains adaptor 24V' }),
  page('stock~compare', 'stock', async (p, h) => { await h.nav('stock'); await h.tab('trends'); await h.clickText(ACTIVE, 'Compare'); },
    { seeded: 'LED300 Black' }),
  page('stock~activity', 'stock', stockActivity, { seeded: 'INV-24' }),
  // Restoring a backup asks first; the question, unanswered. A question has no
  // X and Escape answers it No, so it is measured here, not journeyed.
  page('stock~restore', 'stock', async (p, h) => {
    await stockActivity(p, h); await h.clickText(ACTIVE, 'Restore');
    await h.waitFor(() => !!document.querySelector('.confirm-overlay.show'));
  }, { seeded: 'INV-24' }),
  // A delivery entered by hand: a window opened through another, measured here
  // because its opener goes with the first window, so it has no keyboard journey.
  page('stock~receive-delivery', 'stock', async (p, h) => {
    await stockList(p, h, h.phone); await h.clickText(ACTIVE, 'Receive stock');
    await h.clickText(WINDOW, 'Enter it by hand'); await h.waitFor(() => !!document.querySelector('.modal-overlay.show .sd-dl-win'));
  }, { seeded: 'Clear Etch' }),
  page('team~people', 'team', async (p, h) => { await h.nav('team'); await h.tab('people'); }, { seeded: 'Hattie Brennan' }),
  // A session an admin corrected; the page composes the line from the seeded correction.
  page('team~work', 'team', async (p, h) => { await h.nav('team'); await h.tab('work'); },
    { seeded: 'Closed by Priya Nandakumar', proof: 'left the bench without clocking out' }),
  // A ledger line: the names alone come from the accounts and show with an empty ledger.
  page('team~activity', 'team', async (p, h) => { await h.nav('team'); await h.tab('activity'); }, { seeded: 'price-list-2026.pdf' }),
  page('memory', 'memory', async (p, h) => { await h.nav('memory'); }, { seeded: 'Chase the B-size glass blank reorder' }),
  page('skills', 'skills', async (p, h) => { await h.nav('skills'); }, { seeded: 'Replying to trade accounts' }),
  // Conversations come from localStorage (the seed hands them over in auth.json).
  page('chat', 'chat', async (p, h) => { await h.nav('chat'); await h.waitText('#convos', 'How did September'); await h.evaluate(() => document.getElementById('new-convo').click()); await h.settle(); },
    { seeded: 'How did September sales compare with August?' }),
  page('chat~convo', 'chat', async (p, h) => {
    await h.nav('chat'); await h.waitText('#convos', 'How did September');
    await h.evaluate(t => [...document.querySelectorAll('#convos .convo .title')].find(x => x.textContent.trim().startsWith(t)).click(), 'How did September');
  }, { seeded: 'September was up on August' }),
  page('guide', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('guide'); await h.waitText('#guide-content', 'Your first day'); },
    { static: "the Guide's text is written into the page itself" }),
  page('guide~new', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('new'); await h.waitText('#guide-content', 'Show older releases'); },
    { static: "What's new reads data/changelog.json, the repository's own release notes" }),
  page('guide~requests', 'guide', async (p, h) => {
    await h.nav('guide'); await h.tab('requests'); await h.waitText('#guide-content', 'Warn when a loan unit is overdue by a week');
    await h.evaluate(() => [...document.querySelectorAll('#guide-content .segmented button')].find(b => b.textContent.trim().startsWith('All')).click());
    await h.settle();
  }, { seeded: 'Warn when a loan unit is overdue by a week' }),
  page('guide~design', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('design'); await h.waitFor(() => !!document.querySelector('#guide-content .ds-page')); },
    { static: 'the Design page draws the page\'s own parts with sample content written into the page' }),
  // Customise saves a layout as it closes; prepare() swallows that write.
  page('liability~customise', 'liability', async (p, h) => {
    await h.nav('liability'); await h.waitText('#liability-content', 'Kestrel Logistics Ltd');
    await h.waitFor(() => { const b = document.querySelector('#view-liability [data-wg-customize]'); return b && !b.disabled; });
    await h.click('#view-liability [data-wg-customize]'); await h.waitFor(() => !!document.querySelector('#liability-content.wg-editing'));
  }, { seeded: 'Kestrel Logistics Ltd' }),
  dialog('crm~deal', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('deals'); await h.waitText('#crm-content', 'Fernhill walkway safety signs'); },
    { sel: '#crm-content .crm-card' }, { seeded: 'Fernhill walkway safety signs' }),
  dialog('loans~unit', 'loans', async (p, h) => { await h.nav('loans'); await h.waitText('#loans-content', 'Quayside Exhibitions'); },
    { sel: '#loans-content [title="Edit this unit"]' }, { seeded: 'Edit Loan 1', proof: 'Loan 1' }),
  // The size rule window opens only from the Production Manager's Size check.
  dialog('stock~mapping', 'stock', async (p, h) => { await h.nav('stock'); await h.waitText('.view.active', 'Stock mapping'); },
    { sel: 'button', text: 'Stock mapping' }, { seeded: '1 parked', proof: 'Colour|20' }),
  dialog('stock~item', 'stock', async (p, h) => { await h.nav('stock'); await h.waitText('.view.active', 'Reorder soon'); },
    { sel: '.dt-stock-low .row-open' }, { seeded: 'Lumen Colour Works' }),
  dialog('stock~item-history', 'stock', async (p, h) => { await stockList(p, h, false); },
    { sel: 'button[aria-label="History: Heavy Matt 37.5"]' }, { seeded: 'ref PO-1027', proof: 'PO-1027' }),
  dialog('stock~stocktake', 'stock', async (p, h) => { await stockList(p, h, false); },
    { sel: '.view.active button', text: 'Stock-take' }, { seeded: 'Clear Etch' }),
  dialog('stock~draft-order', 'stock', stockReorder, { sel: '.view.active button', text: 'Draft order' }, { seeded: 'Brightway Lighting' }),
  dialog('stock~receive-one', 'stock', stockReorder, { sel: '.view.active button', text: 'Receive' }, { seeded: 'LED80 White' }),
  dialog('stock~supplier-edit', 'stock', stockSuppliers, { sel: '.view.active button', text: 'Edit details' }, { seeded: 'Brightway Lighting' }),
  dialog('stock~compose', 'stock', stockSuppliers, { sel: '.view.active button', text: 'Compose reorder email' }, { seeded: 'LED80 White' }),
  dialog('stock~close-quarter', 'stock', stockActivity, { sel: '.view.active button', text: 'Close quarter and start new' }, { seeded: 'Q4 2026' }),
  dialog('sizes~rule', 'labels', async (p, h) => {
    await labelsBefore(p, h); await h.queue('make'); await h.click('#labels-content .more-btn');
    await h.clickText('.dmenu', 'Size check'); await h.waitText('#labels-content', 'Moonbeam Profile 300');
  }, { sel: '#labels-content button', text: 'Resolve' }, { seeded: 'Moonbeam Profile 300' }),
];
