# ---- What the app is allowed to ask Shopify for -----------------------------

@test
def t_the_app_asks_for_no_scope_it_cannot_use():
    """85 scopes were granted; a stolen token reached all of them. Each one
    removed had no trace anywhere in the app AND no bearing on a dispatch, CRM
    or finance desk.

    Pinned as an explicit list rather than a count, because the failure mode is
    a scope creeping back in during an unrelated change - and re-granting one
    costs a reinstall of the app on a live store."""
    import io as _io, re as _re
    toml = _io.open(os.path.join(os.path.dirname(__file__), "..", "shopify.app.toml"),
                    encoding="utf-8").read()
    scopes = set(x for x in _re.search(r'scopes = "([^"]*)"', toml).group(1).split(",") if x)
    # Deliberately dropped. Anything here reappearing means someone widened the
    # app's reach, and that should be a decision, not a diff nobody read.
    gone = {"read_gift_cards", "read_metaobjects", "read_themes", "read_script_tags",
            "read_customer_payment_methods", "read_audit_events", "read_pixels",
            "read_store_credit_accounts", "read_cart_transforms", "read_price_rules",
            "read_marketing_events", "read_publications", "read_reports"}
    back = sorted(scopes & gone)
    ok(not back, "scopes that came back without a decision: " + str(back))
    # And the ones the desk actually runs on must never be dropped by accident.
    need = {"read_orders", "write_orders", "read_customers", "read_products",
            "read_fulfillments", "write_fulfillments", "read_inventory",
            "read_files", "read_shipping", "read_all_orders"}
    missing = sorted(need - scopes)
    ok(not missing, "scopes the dispatch desk needs, now missing: " + str(missing))
    ok(len(scopes) < 50, f"the ask stays trimmed (currently {len(scopes)})")


@test
def t_the_privacy_webhooks_are_declared_where_shopify_reads_them():
    """The handlers exist, but Shopify only sends to URLs declared in the app
    config - and only after `shopify app deploy`. Code without this block is a
    compliance gap that looks finished."""
    import io as _io, tomllib
    path = os.path.join(os.path.dirname(__file__), "..", "shopify.app.toml")
    d = tomllib.load(open(path, "rb"))
    pc = (d.get("webhooks") or {}).get("privacy_compliance") or {}
    for key in ("customer_data_request_url", "customer_deletion_url", "shop_deletion_url"):
        ok(key in pc, f"{key} is declared")
        ok(str(pc[key]).endswith("/webhooks/privacy"),
           f"{key} points at the receiver that actually handles it")


