# World Options Ecommerce REST API — contract notes

Source: live OpenAPI 3 spec at `https://ecommerce.worldoptions.com/api/docs.json`
(human docs at `/api/docs`, ReDoc at `/api/docs?ui=re_doc`). Symfony API Platform.
Saved copy of the spec: kept out of the repo; re-fetch the JSON if fields change.

- **Base URL (live, UK):** `https://ecommerce.worldoptions.com`
- **Prelive/staging:** `https://prelive-ecommerce.worldoptions.com` (region variants exist, e.g. AU)
- **Auth:** every call needs header `X-AUTH-TOKEN: <merchant API key>` (OpenAPI
  securityScheme `X_AUTH_TOKEN`, type apiKey, in header). This is the API key the
  merchant gets from the World Options portal / Shopify integration page.
  `POST /api/customers/authorize` (username/password/meternumber/country) and
  `POST /api/shops/authorize` exist for the portal-connect/install flow and return
  `{success: bool}`; we do not need them when we already hold an X-AUTH-TOKEN.
- **Validate a key:** `GET /api/customers/info` or `GET /api/shops/info` (200 = good).

## Dispatch flow

1. **Quote** — `POST /api/rates` (free, read-only). Body:
   - `origin` / `destination`: `{name, company, firstname, lastname, street, postcode,
     city, state, country (ISO2), phone, email}`
   - `items[]`: `{name, reference (SKU), productId, variantId, quantity, price,
     dimensions:[{width, length, depth, weight}]}` (cm / kg, floats)
   - or `boxes[]`: `{width, length, depth, weight}` — simplest: one box, total weight.
   - `currency` (e.g. "GBP"), `residental` (bool), `packing` (bool), `order` (WO order id, optional)
   - Response `Rate-rate.read`: `id` (the **Rate ID**), plus grouped priced options:
     `webservicesRates[]`, `internalRates[]`, `customRates[]`, `backupRates[]`. Each has
     `carriersServices[]` = `{id (**RateCarrier ID** — the pick), carrierService:{name,code,carrier},
     amount, package, delivery, currency, dropOffPoint[]}`.
   - `POST /api/rates/multi` = same but `{currency, packing, order, data:[{origin,destination,items,boxes}]}`.
2. **Book** — `POST /api/shipments` (this **books and charges** the WO account). Body:
   `{rate: <Rate ID>, carrier: <RateCarrier ID chosen from the rate>, order: <WO order id, optional>}`.
   Response `Shipment-shipment.read`: `{id, trackingNumber, shippingAmount, currency,
   carrierService:{name,code,carrier}, shippingLabels:[string], canceled, invoice, locationId, order}`.
   `shippingLabels[]` are the label outputs (treat as URL or base64 defensively).
3. **Label (thermal)** — `POST /api/certificate?id=<shipmentId>` and `POST /api/signature?id=`.
   The shipment's `shippingLabels[]` is the primary label; certificate/signature are extras.
4. **Track** — `GET /api/shipments/{trackingNumber}/get` → `Shipment-shipment.read`.
5. **Cancel** — `PATCH /api/shipments/{trackingNumber}/cancel`.
6. **Docs** — `GET /api/orders/{orderId}/invoices` (commercial invoice),
   `POST /api/orders/{orderId}/documents` (email docs to an address).

## Reference data (GET, cache)
`/api/carriers`, `/api/carrier_services`, `/api/countries/wo` (WO-supported countries),
`/api/currencies`, `/api/zones`, `/api/provinces`. Saved catalogue: `/api/boxes`,
`/api/products`, `/api/product_dimensions`. Orders mirror: `POST /api/orders`
`{orderId (external id), reference, amount, currency, data[]}`.

## Notes for our build
- Confine every WO call to `worldoptions.py`; the rest of the app talks to our own
  internal shape so the provider can be swapped in one file.
- Quoting is free; only `POST /api/shipments` spends money — gate it behind an explicit
  merchant confirm showing carrier + price. Never expose booking to the AI chat.
- We ship one box per order by default (gobos are small, uniform): merchant confirms/edits
  weight + box preset in the Dispatch panel.
- After a successful booking, create the Shopify fulfillment (modern fulfillment-orders
  flow) with tracking, and move the order tag to Dispatched.
