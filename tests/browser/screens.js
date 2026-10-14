// The states the suite measures. Each `go` ends by waiting for content only
// the seed puts there, so an empty state is never measured by mistake.
// Never click anything that writes: open tabs, rows and dialogs only.
const dialog = (id, view, before, opener) => ({
  id, view, kind: 'dialog', before, opener,
  go: async (page, h) => {
    await before(page, h);
    await page.evaluate(({ sel, text }) => {
      const e = [...document.querySelectorAll(sel)].filter(x => x.offsetParent || x.getClientRects().length)
        .find(x => !text || (x.innerText || '').trim().startsWith(text));
      if (!e) throw new Error('no opener ' + sel + ' ' + (text || ''));
      e.setAttribute('data-suite-opener', '');
      e.click();
    }, opener);
    await page.waitForSelector('.modal-overlay.show .modal');
    await h.settle();
  },
});
const page = (id, view, go) => ({ id, view, kind: 'page', go });

const crmBefore = async (p, h) => { await h.nav('crm'); await p.waitForSelector('#crm-content .tabs'); };
const labelsBefore = async (p, h) => { await h.nav('labels'); await h.waitText('#labels-content', '#210388'); };

module.exports = [
  page('overview', 'overview', async (p, h) => { await h.nav('overview'); await h.waitText('#ov-content', 'Revenue is up on last week'); }),
  page('seo', 'seo', async (p, h) => { await h.nav('seo'); await h.waitText('#seo-content', 'The store is indexable'); }),
  page('keywords', 'keywords', async (p, h) => { await h.nav('keywords'); await h.waitText('#keywords-content', 'custom gobo'); }),
  // 'Load products' is a read: POST /api/products {months, fresh}, no AI, no store write.
  page('products', 'products', async (p, h) => { await h.nav('products'); await h.click('#products-content .run-gate .btn-primary'); await h.waitText('#products-content', 'Walkway Safety Sign Gobo', 40000); }),
  page('customers', 'customers', async (p, h) => {
    await h.nav('customers'); await h.waitText('#customers-content', 'Champions');
    await h.waitFor(() => { const s = document.querySelector('#trade-radar-slot'); return s && s.innerText.trim().length > 20; });
  }),
  page('liability', 'liability', async (p, h) => { await h.nav('liability'); await h.waitFor(() => !!document.querySelector('#liability-content [data-widget="owing"] .dt-row'), null, 30000); }),
  page('recon', 'recon', async (p, h) => { await h.nav('recon'); await h.waitFor(() => !!document.querySelector('#recon-content .dt-row.click')); }),
  page('forecast', 'forecast', async (p, h) => { await h.nav('forecast'); await h.waitFor(() => { const c = document.querySelector('#forecast-content'); return c && !c.innerText.includes('Loading') && c.innerText.includes('Expected this month'); }); }),
  page('connector', 'connector', async (p, h) => { await h.nav('connector'); await h.waitFor(() => { const c = document.querySelector('#connector-content'); return c && c.innerText.includes('Xero linked') && c.innerText.includes('Runs'); }); }),
  page('labels', 'labels', labelsBefore),
  page('labels~make-open', 'labels', async (p, h) => { await labelsBefore(p, h); await h.click('#labels-content .lbl-qrow'); await p.waitForSelector('#labels-content .lbl-preview'); await h.settle(); }),
  page('labels~shipments', 'labels', async (p, h) => { await h.nav('labels'); await h.queue('shipments'); await h.waitText('#labels-content', 'Replacement gobo'); }),
  page('sizes', 'sizes', async (p, h) => { await h.nav('sizes'); await p.waitForSelector('#sizes-content tr.sizes-row'); await h.settle(); }),
  page('crm~leads', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('leads'); await h.waitText('#crm-content', 'Rental stock enquiry'); }),
  page('crm~activities', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('activities'); await h.waitText('#crm-content', 'Site visit for window throw'); }),
  page('crm~insights', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('insights'); await h.waitText('#crm-content', 'Won by month'); }),
  page('crm~contacts', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('contacts'); await h.waitText('#crm-content', 'Marcus Bell'); }),
  page('loans', 'loans', async (p, h) => { await h.nav('loans'); await h.waitText('#loans-content', 'Quayside Exhibitions'); }),
  // Never open a thread here: opening one marks it read, a Gmail write.
  page('mail', 'mail', async (p, h) => { await h.nav('mail'); await h.waitText('#mail-content', 'Artwork for the autumn tour gobos'); }),
  page('files', 'files', async (p, h) => { await h.nav('files'); await h.waitText('#files-content', 'Artwork'); }),
  page('team~people', 'team', async (p, h) => { await h.nav('team'); await h.tab('people'); await h.waitText('#team-content', 'Hattie Brennan'); }),
  page('team~work', 'team', async (p, h) => { await h.nav('team'); await h.tab('work'); await h.waitText('#team-content', 'Recent sessions'); await h.waitText('#team-content', 'Jonah Featherstone'); }),
  page('team~activity', 'team', async (p, h) => { await h.nav('team'); await h.tab('activity'); await h.waitText('#team-content', 'Jonah Featherstone'); }),
  page('memory', 'memory', async (p, h) => { await h.nav('memory'); await h.waitText('#memory-content', 'Tracked changes'); }),
  page('skills', 'skills', async (p, h) => { await h.nav('skills'); await h.waitText('#skills-content', 'Quoting custom gobos'); }),
  // Conversations come from localStorage (the seed hands them over in auth.json).
  page('chat', 'chat', async (p, h) => { await h.nav('chat'); await h.waitText('#convos', 'How did September'); await h.evaluate(() => document.getElementById('new-convo').click()); await h.settle(); }),
  page('chat~convo', 'chat', async (p, h) => {
    await h.nav('chat'); await h.waitText('#convos', 'How did September');
    await h.evaluate(t => [...document.querySelectorAll('#convos .convo .title')].find(x => x.textContent.trim().startsWith(t)).click(), 'How did September');
    await h.waitText('#view-chat', 'September was up on August');
  }),
  page('guide', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('guide'); await h.waitText('#guide-content', 'Your first day'); }),
  page('guide~new', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('new'); await h.waitText('#guide-content', 'Show older releases'); }),
  page('guide~requests', 'guide', async (p, h) => {
    await h.nav('guide'); await h.tab('requests'); await h.waitText('#guide-content', 'Warn when a loan unit is overdue by a week');
    await h.evaluate(() => [...document.querySelectorAll('#guide-content .segmented button')].find(b => b.textContent.trim().startsWith('All')).click());
    await h.settle();
  }),
  page('guide~design', 'guide', async (p, h) => { await h.nav('guide'); await h.tab('design'); await h.waitFor(() => !!document.querySelector('#guide-content .ds-page')); }),
  // Customise saves a layout as it closes; prepare() swallows that write.
  page('customers~customise', 'customers', async (p, h) => {
    await h.nav('customers'); await h.waitText('#customers-content', 'Champions');
    await h.waitFor(() => { const b = document.querySelector('#view-customers [data-wg-customize]'); return b && !b.disabled; });
    await h.click('#view-customers [data-wg-customize]'); await h.waitFor(() => !!document.querySelector('#customers-content.wg-editing'));
  }),
  page('overview~customise', 'overview', async (p, h) => {
    await h.nav('overview'); await h.waitText('#ov-content', 'Revenue is up on last week');
    await h.waitFor(() => { const b = document.querySelector('#view-overview [data-wg-customize]'); return b && !b.disabled; });
    await h.click('#view-overview [data-wg-customize]'); await h.waitFor(() => !!document.querySelector('#ov-content.wg-editing'));
  }),
  dialog('crm~deal', 'crm', async (p, h) => { await crmBefore(p, h); await h.tab('deals'); await h.waitText('#crm-content', 'Fernhill walkway safety signs'); }, { sel: '#crm-content .crm-card' }),
  dialog('loans~unit', 'loans', async (p, h) => { await h.nav('loans'); await h.waitText('#loans-content', 'Quayside Exhibitions'); }, { sel: '#loans-content [title="Edit this unit"]' }),
  // The size rule window opens only from the Production Manager's Size check.
  dialog('sizes~rule', 'labels', async (p, h) => {
    await labelsBefore(p, h); await h.queue('make'); await h.click('#labels-content .more-btn');
    await h.clickText('.dmenu', 'Size check'); await h.waitText('#labels-content', 'Moonbeam Profile 300');
  }, { sel: '#labels-content button', text: 'Resolve' }),
];
