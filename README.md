# Shopify MCP Server

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that connects Claude directly to your Shopify store. Manage products, orders, customers, collections, inventory, and fulfillments — all through natural language.

---

## What you can do with this

Once connected, you can talk to your Shopify store like this:

- *"Show me all unfulfilled orders from today"*
- *"Create a new product called Summer T-Shirt, price €29.99, set it to draft"*
- *"How many active products do we have?"*
- *"Search for customers with the email john@example.com"*
- *"Update inventory for product 123 to 50 units"*

---

## Requirements

- Python 3.11 or higher
- A Shopify store (any plan)
- A Claude.ai Pro, Team, or Enterprise account (for remote MCP connections)

---

## Step 1 — Get your Shopify credentials

You need two things: your **store name** and an **Admin API access token**.

### Find your store name

Your store name is the part before `.myshopify.com`.
Example: if your admin URL is `https://acme-store.myshopify.com/admin`, your store name is `acme-store`.

### Create a Custom App and get your access token

> ⚠️ **Important:** A regular Shopify API key will NOT work. You need an **Admin API access token** from a Custom App. Follow these steps exactly.

1. Go to **Shopify Admin** → **Settings** → **Apps and sales channels**
2. Click **Develop apps** in the top right corner
3. If prompted, click **Allow custom app development**
4. Click **Create an app**, give it a name (e.g. `MCP Server`), click **Create app**
5. Go to the **Configuration** tab → click **Configure Admin API scopes**
6. Enable the scopes you need. For full access, select:
   - `read_products`, `write_products`
   - `read_orders`, `write_orders`
   - `read_customers`, `write_customers`
   - `read_inventory`, `write_inventory`
   - `read_fulfillments`, `write_fulfillments`
   - `read_webhooks`, `write_webhooks`
7. Click **Save**
8. Go to the **API credentials** tab → click **Install app** → confirm
9. Click **Reveal token once** and copy the token immediately — it starts with `shpat_`

> 💡 Shopify only shows this token once. If you lose it, go back to API credentials, uninstall the app, then reinstall to generate a new one.

---

## Step 2 — Set up the server locally

### Clone this repo

```bash
git clone https://github.com/daanjonk/shopify-mcp.git
cd shopify-mcp
```

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure your environment variables

```bash
cp env.example .env
```

Open `.env` and fill in your values:

```env
SHOPIFY_STORE=your-store-name
SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxx
```

> Only these two are required. Leave everything else as-is.

### Run the server

```bash
python server.py
```

You should see output like:

```
INFO  Token mode: static SHOPIFY_ACCESS_TOKEN (no auto-refresh)
INFO  Uvicorn running on http://0.0.0.0:8000
```

Your MCP server is running at `http://localhost:8000/mcp`.

---

## Step 3 — Deploy to the cloud

To use this server with Claude.ai, it needs a public URL. The easiest option is **Railway** — the free tier is enough to get started.

### Deploy on Railway

1. Fork this GitHub repo to your own account
2. Go to [railway.app](https://railway.app) and sign in with GitHub
3. Click **New Project** → **Deploy from GitHub repo**
4. Select your forked `shopify-mcp` repo
5. Railway detects the `Dockerfile` and starts building automatically
6. Once the build completes, go to your service → **Settings** → **Networking** → **Generate Domain**
7. Copy your public URL — it looks like `https://shopify-mcp-production.up.railway.app`

### Add your environment variables on Railway

In your Railway project, go to **Variables** and add the following:

| Variable | Value |
|---|---|
| `SHOPIFY_STORE` | `your-store-name` |
| `SHOPIFY_ACCESS_TOKEN` | `shpat_xxxxxxxxxxxxxxxxxxxx` |
| `PORT` | `8000` |
| `MCP_TRANSPORT` | `streamable-http` |

Railway restarts your server automatically after saving.

---

## Step 4 — Connect to Claude

### Your MCP endpoint URL

Combine your Railway URL with `/mcp`:

```
https://your-app.up.railway.app/mcp
```

### Add the server in Claude.ai

> ⚠️ **Authentication token:** When adding a remote MCP server in Claude.ai, it will ask for an authentication token. This is a security token that protects your server endpoint — it is **separate** from your Shopify access token.

**To connect:**

1. Go to [claude.ai](https://claude.ai) → click your profile icon (bottom left) → **Settings**
2. Navigate to **Integrations**
3. Click **Add integration**
4. Fill in:
   - **Name:** `Shopify`
   - **URL:** `https://your-app.up.railway.app/mcp`
5. For the **authentication token** field: paste the same value you set for `MCP_BEARER_TOKEN` (see below). The `/mcp` endpoint stays locked until this is set.

### The /mcp endpoint is locked by default

This server fails closed. The `/mcp` endpoint exposes the full Shopify tool set (including writes and customer data), so it returns **503 Service Unavailable** until you set a bearer token. The check is already built into the code (constant-time comparison); there is nothing to add to `server.py`.

**Step 1 — Set `MCP_BEARER_TOKEN` in Railway:**

Under Variables, add a long random string:

```
MCP_BEARER_TOKEN=pick-a-long-random-string-here
```

Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

**Step 2 — Enter the same value in Claude:**

When adding the integration in Claude.ai, paste your `MCP_BEARER_TOKEN` value into the **authentication token** field. Any request without a matching `Authorization: Bearer <token>` header is rejected.

> The embedded Store Copilot (the in-admin chat) does not use this token. It is authenticated separately with Shopify session tokens and is strictly read-only.

---

## Available tools

| Tool | Description |
|---|---|
| `shopify_list_products` | List products with optional filters |
| `shopify_get_product` | Get a single product by ID |
| `shopify_create_product` | Create a new product |
| `shopify_update_product` | Update an existing product |
| `shopify_delete_product` | Permanently delete a product |
| `shopify_count_products` | Count products (with filters) |
| `shopify_list_orders` | List orders with filters |
| `shopify_get_order` | Get a single order by ID |
| `shopify_count_orders` | Count orders |
| `shopify_close_order` | Close an order |
| `shopify_cancel_order` | Cancel an order |
| `shopify_list_customers` | List customers |
| `shopify_search_customers` | Search customers by name/email |
| `shopify_get_customer` | Get a single customer by ID |
| `shopify_create_customer` | Create a new customer |
| `shopify_update_customer` | Update an existing customer |
| `shopify_get_customer_orders` | Get all orders for a customer |
| `shopify_list_collections` | List custom or smart collections |
| `shopify_get_collection_products` | Get products in a collection |
| `shopify_list_locations` | List inventory locations |
| `shopify_get_inventory_levels` | Get current inventory levels |
| `shopify_set_inventory_level` | Set inventory quantity at a location |
| `shopify_list_fulfillments` | List fulfillments for an order |
| `shopify_create_fulfillment` | Fulfill (ship) an order |
| `shopify_get_shop` | Get store info (name, currency, plan, etc.) |
| `shopify_list_webhooks` | List configured webhooks |
| `shopify_create_webhook` | Create a new webhook |

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SHOPIFY_STORE` | ✅ | — | Store name, e.g. `my-store` (not the full URL) |
| `SHOPIFY_ACCESS_TOKEN` | ✅* | — | Admin API token from Custom App (`shpat_...`) |
| `SHOPIFY_CLIENT_ID` | No | — | OAuth client ID (advanced, replaces static token) |
| `SHOPIFY_CLIENT_SECRET` | No | — | OAuth client secret (advanced) |
| `SHOPIFY_API_VERSION` | No | `2024-10` | Shopify Admin API version |
| `PORT` | No | `8000` | Port the server listens on |
| `MCP_TRANSPORT` | No | `streamable-http` | Transport protocol |
| `MCP_BEARER_TOKEN` | Yes for `/mcp` | n/a | Locks the `/mcp` endpoint; `/mcp` returns 503 until set. Use the same value in Claude. |

**Embedded Store Copilot** (the in-admin chat) needs `ANTHROPIC_API_KEY`, `SHOPIFY_API_KEY` (or `SHOPIFY_CLIENT_ID`), `SHOPIFY_API_SECRET` (or `SHOPIFY_CLIENT_SECRET`), and `SHOPIFY_STORE`. Optionally set `APP_BASE_URL` (your public URL) for the Google OAuth redirect. See `env.example` for the full, commented list.

*Either `SHOPIFY_ACCESS_TOKEN` **or** `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` is required.

---

## Troubleshooting

**"Authentication failed" (401)**
Your `SHOPIFY_ACCESS_TOKEN` is wrong or expired. Make sure it starts with `shpat_` and that the Custom App is installed on your store.

**"Permission denied" (403)**
Your token is missing required API scopes. Go back to your Custom App → Configuration → add the missing scopes → Save → reinstall the app (this generates a new token).

**"Missing SHOPIFY_STORE environment variable"**
Check that `SHOPIFY_STORE` is set to just the store name — not the full URL.
✅ `my-store` &nbsp; ❌ `my-store.myshopify.com` &nbsp; ❌ `https://my-store.myshopify.com`

**Claude can't connect to the server**
Make sure your Railway deployment is active and a domain is generated. Test by opening `https://your-app.up.railway.app/mcp` in a browser — you should get a response, not a 404.

**I lost my Shopify access token**
Shopify only shows it once. Go to Shopify Admin → Settings → Apps → your app → API credentials → Uninstall app → Install app again → Reveal token once.

---

## License

MIT
