// Every window the seeded world can open without saving anything, for the
// keyboard journeys (keyboard.spec.js), beyond the three that screens.js
// measures at three sizes. These are not measured, so they are not in the
// record. Each is reached by a button (sel, and the text it starts with) or
// by an item of a dropdown menu (the menu's button, and the item's text):
// closing a window opened from a menu gives focus back to the menu's button.
const labels = async (p, h) => { await h.nav('labels'); await h.waitText('#labels-content', '#210388'); };
const overview = async (p, h) => { await h.nav('overview'); await h.waitText('#ov-content', 'Revenue is up on last week'); };
const mail = async (p, h) => { await h.nav('mail'); await h.waitText('#mail-content', 'Artwork for the autumn tour gobos'); };
const more = item => ({ sel: '#labels-content .more-btn', item });

module.exports = [
  { id: 'pm~size-rules', before: labels, menu: more('Size rules') },
  { id: 'pm~dispatch-manifest', before: labels, menu: more('Dispatch manifest') },
  { id: 'pm~stock-usage', before: labels, menu: more('Stock usage') },
  { id: 'pm~margins', before: labels, menu: more('Margins') },
  { id: 'pm~shipping-settings', before: labels, menu: more('Shipping settings') },
  { id: 'pm~new-shipment', before: labels, opener: { sel: '#labels-content button', text: 'New shipment' } },
  { id: 'pm~edit-order', before: labels, opener: { sel: '#labels-content button[title="Change the delivery address or contact details"]' } },
  { id: 'chart', before: overview, opener: { sel: '#view-overview .chart-expand' } },
  { id: 'settings', before: overview, menu: { sel: '#side-user', item: 'Settings' } },
  { id: 'inbox~compose', before: mail, opener: { sel: '#mail-content button', text: 'Compose' } },
];
