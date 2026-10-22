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
        .find(x => !text || (x.innerText || '').trim().startsWith(text));
      if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
      e.setAttribute('data-suite-opener', '');
      e.click();
    }, opener);
    await p.waitForSelector(WINDOW);
    await h.waitText(WINDOW, o.seeded);
  },
});

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
  dialog('sizes~rule', 'labels', async (p, h) => {
    await labelsBefore(p, h); await h.queue('make'); await h.click('#labels-content .more-btn');
    await h.clickText('.dmenu', 'Size check'); await h.waitText('#labels-content', 'Moonbeam Profile 300');
  }, { sel: '#labels-content button', text: 'Resolve' }, { seeded: 'Moonbeam Profile 300' }),
];
