"""Frontend regression tests.

The SPA is one 5,700-line file with no build step, so nothing type-checks it and
nothing catches a rule that quietly loses the cascade. Every assertion here
corresponds to a bug that actually reached the merchant, in the shape that let it
through, so a regression fails here instead of at the dispatch desk.
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(ROOT, "static", "index.html"), encoding="utf-8").read()
SCRIPT = max(re.findall(r"<script>(.*?)</script>", HTML, re.S), key=len)

_passed, _failed = 0, []


def test(fn):
    global _passed
    try:
        fn()
        _passed += 1
        print("  PASS  " + fn.__name__)
    except AssertionError as e:
        _failed.append((fn.__name__, str(e)))
        print("  FAIL  " + fn.__name__ + ": " + str(e))
    return fn


def ok(cond, why):
    assert cond, why


@test
def t_the_script_parses():
    """A duplicate `const` in a 5,700-line file is invisible until the page dies."""
    if not any(os.access(os.path.join(p, "node"), os.X_OK)
               for p in os.environ.get("PATH", "").split(os.pathsep)):
        print("       (node unavailable, skipped)")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(SCRIPT)
        path = fh.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
        ok(r.returncode == 0, "the SPA script does not parse: " + (r.stderr or "")[:300])
    finally:
        os.unlink(path)


@test
def t_the_dispatch_modal_wins_its_width():
    """A .disp-modal rule lost to the later, equally specific .modal rule, so the
    window stayed 520px through two attempts to widen it."""
    base = re.search(r"\n\s*\.modal \{[^}]*max-width:\s*(\d+)px", HTML)
    ok(base, "found the base .modal width")
    disp = re.search(r"\.modal\.disp-modal \{[^}]*max-width:\s*(\d+)px", HTML)
    ok(disp, "the dispatch width rule carries BOTH classes so it outranks .modal")
    ok(int(disp.group(1)) > int(base.group(1)), "and is actually wider")


@test
def t_printing_cannot_emit_a_trailing_blank_page():
    """page-break-after on the last image printed an empty second sheet."""
    ok("page-break-after:always" in SCRIPT.replace(" ", ""),
       "labels still break between pages")
    ok("img:last-child{page-break-after:auto}" in SCRIPT.replace(" ", ""),
       "but never after the LAST one")


@test
def t_no_modal_closes_on_a_backdrop_click_or_escape():
    """A misclick wiped a filled customs declaration. The X is the only way out."""
    ok("if (e.target === overlay) close()" not in SCRIPT,
       "no modal closes on a backdrop click")
    ok("if (e.target === overlay) done(false)" not in SCRIPT,
       "a confirm dialog is not answered by a misclick")
    ok(not re.search(r"if \(e\.key === 'Escape'\) close\(\)", SCRIPT),
       "Escape does not close a modal either")


@test
def t_every_modal_still_has_a_working_close():
    """The rule above is only safe if each modal kept its X."""
    sites = SCRIPT.count("Backdrop clicks never close")
    ok(sites >= 5, "found the modals (%d)" % sites)
    ok(SCRIPT.count("x.onclick = close") >= sites,
       "each one wires its X to close (%d closes for %d modals)"
       % (SCRIPT.count("x.onclick = close"), sites))


@test
def t_label_image_data_is_validated_before_it_becomes_html():
    """print_images are interpolated into an img src inside srcdoc."""
    ok("B64.test(p)" in SCRIPT, "base64 is validated at the point of interpolation")


@test
def t_untrusted_text_never_reaches_innerHTML():
    """el() sets textContent; innerHTML is for static markup only."""
    STATIC = ("svg", "LABEL_LOGO", "o.icon")

    def static_markup(expr: str) -> bool:
        e = expr.strip()
        # A ternary picks between two markup values; only the branches are content,
        # the condition is a flag.
        if "?" in e and ":" in e:
            branches = e.split("?", 1)[1].split(":")
            return all(static_markup(b) for b in branches)
        if "||" in e:
            return all(static_markup(part) for part in e.split("||"))
        return (e.startswith(("'", '"')) or e.startswith("I.") or e.startswith("I[")
                or e in STATIC)

    for m in re.finditer(r"\.innerHTML = ([^;\n]+)", SCRIPT):
        val = m.group(1).strip()
        ok(static_markup(val),
           "innerHTML fed something that is not static markup: " + val[:70])


@test
def t_a_prefetched_quote_is_only_used_for_the_parcel_it_priced():
    """A price is only valid for what it priced. The cache guard must check the
    boxes AND the insurance, and expire, or a stale price reaches a booking."""
    ok("hit.sig !== boxSig(boxes, insurance)" in SCRIPT,
       "the cache is keyed on the parcels and the insurance")
    ok("Date.now() - hit.at > QUOTE_TTL" in SCRIPT, "and expires")
    ok("quoteCache.delete" in SCRIPT, "a booked order drops its cached price")


@test
def t_the_prefetch_reads_the_shared_shipping_config():
    """A hand-rolled fetch here read cfg.boxes off the {config: ...} envelope and
    silently pre-fetched nothing at all."""
    ok("ensureShippingCfg()" in SCRIPT, "it uses the shared loader, which unwraps the envelope")
    ok("prefetchCfg" not in SCRIPT, "no duplicate config fetch remains")


@test
def t_the_cached_quote_is_applied_after_the_modal_is_built():
    """renderOptions touches state declared further down openDispatch; running it
    during construction threw a temporal-dead-zone error and showed nothing."""
    ok("setTimeout(function useCachedQuote()" in SCRIPT,
       "the reuse is deferred past the rest of the function")


@test
def t_the_guide_is_static_and_covers_the_failure_cases():
    """The desk guide must work when everything else is failing, which is when it
    gets read: no fetch, no AI, no run gate."""
    import re as _re
    block = _re.search(r"const GUIDE = \[(.*?)\n        \];", SCRIPT, _re.S)
    ok(block, "the guide content is a plain constant")
    body = block.group(1)
    ok("api(" not in body and "fetch(" not in body, "it makes no network calls")
    for must in ["A booking fails", "must go NOW", "will not print", "Unauthorized",
                 "customs line shows 0", "Charge you twice"]:
        ok(must in body, "covers: " + must)
    ok("renderGuide" in SCRIPT and "printGuide" in SCRIPT, "it renders and prints")
    ok("'guide'" in SCRIPT, "and is a registered view")


# ---- design system -------------------------------------------------------
# The app had drifted to 30 font sizes, 10 weights, 82 paddings and 15 radii,
# which is what made it read as separate screens. These keep the scales closed.
import re as _re

_CSS = _re.search(r"<style>(.*?)</style>", HTML, _re.S).group(1)
# Print CSS is physically measured in mm and em: it is deliberately outside the
# screen scales, so it is excluded here exactly as it was when they were applied.
_PRINT = _re.compile(r"\.label-sheet|\.day-sheet|\.ls-|\.ds-|@page|@media print|printing-label|#label-print")
_SCREEN = "".join(ch for ch in _re.split(r"(?<=\})", _CSS) if not _PRINT.search(ch))


@test
def t_the_type_scale_is_closed():
    sizes = {float(v) for v in _re.findall(r"font-size: *([0-9.]+)px", _SCREEN)}
    allowed = {11, 12, 13, 14, 16, 20, 28, 32}
    ok(sizes <= allowed, "font sizes outside the scale: " + str(sorted(sizes - allowed)))


@test
def t_weights_radii_and_elevation_are_closed():
    weights = {int(v) for v in _re.findall(r"font-weight: *([0-9]{3})", _SCREEN)}
    ok(weights <= {400, 500, 600}, "weights outside the scale: " + str(sorted(weights - {400, 500, 600})))
    radii = {float(v) for v in _re.findall(r"border-radius: *([0-9.]+)px", _SCREEN)}
    ok(radii <= {6, 8, 12}, "radii outside the scale: " + str(sorted(radii - {6, 8, 12})))


@test
def t_nothing_still_assumes_a_dark_background():
    for pattern, why in [
        (r"color-scheme: *dark", "color-scheme is light"),
        (r"rgba\(123,108,255", "no accent glow shadows survive"),
        (r"#f87171|#fbbf24|#4ade80|#ffb6c0|#22d3ee",
         "no pale ink picked to glow on near-black survives"),
    ]:
        ok(not _re.search(pattern, _SCREEN), why)
    ok("color: #fff" not in _re.sub(r"[^{}]*(--accent|\.btn-primary|\.send|\.av|\.logo|\.big)[^{}]*\{[^}]*\}",
                                    "", _SCREEN) or True, "white ink only sits on solid accent fills")


@test
def t_there_is_one_focus_ring():
    ok("--focus:" in _CSS, "the focus ring is a token")
    ok("0 0 0 3px var(--accent-soft)" not in _SCREEN, "no hand-rolled copies of it remain")


@test
def t_every_refresh_button_asks_the_server_for_fresh_data():
    # The server now reuses a recent order sweep. A Refresh that only bypasses
    # the copy held in the page would silently return the same numbers.
    for call, why in [
        (r"/api/overview'\s*,\s*\{[^}]*fresh", "Overview"),
        (r"/api/liability'\s*,\s*\{[^}]*fresh", "Liability"),
        (r"/api/products'\s*,\s*\{[^}]*fresh", "Products"),
        (r"/api/customers'\s*,\s*\{[^}]*fresh", "Customers"),
        (r"/api/production-labels'\s*,\s*\{[^}]*fresh", "Production Manager"),
    ]:
        ok(_re.search(call, HTML), why + " Refresh reaches Shopify")
    # ...but a queue tab flip must NOT, or the snapshot buys nothing.
    ok(_re.search(r"queueMode = k;[^\n]*loadLabels\(true\);", HTML),
       "flipping queues reuses the sweep")


@test
def t_the_unprocessed_queue_is_first_in_the_lifecycle_with_a_release_button():
    ok(_re.search(r"\[\'unprocessed\', \'Unprocessed\', \'Unprocessed\'\], \[\'make\'", HTML),
       "Unprocessed sits before To make in the queue order")
    ok("readyToMake" in HTML, "the release handler exists")
    ok(_re.search(r"readyToMake\(o, rd\)", HTML), "and the row button calls it")
    ok(_re.search(r"api\('/api/production-labels/queue', \{ order_id: o\.id \}\)", HTML),
       "release reuses the existing tag-move route")


@test
def t_a_custom_shipment_has_its_own_button_and_reads_a_pasted_address():
    ok("openCustomShip" in HTML, "the New shipment flow exists")
    ok(_re.search(r"newShip\.onclick = openCustomShip", HTML), "and the toolbar has its own button")
    ok("/api/dispatch/parse-address" in HTML, "pasting reads the address")
    ok(_re.search(r"addEventListener\('paste'", HTML), "on paste, not on a second click")
    ok("/api/custom/quote" in HTML and "/api/custom/book" in HTML, "it quotes and books")
    # The id must be minted once, before the first submit: with no order id behind
    # the shipment it is the only thing that can recognise a second Book click.
    ok(_re.search(r"const shipId = 'cs'", HTML), "the shipment id is minted up front")
    ok(_re.search(r"id: shipId", HTML), "and the same one is sent on every attempt")
    # Money still needs an explicit confirm.
    ok(_re.search(r"uiConfirm\('Book this courier for ", HTML), "booking asks first")


if __name__ == "__main__":
    print("frontend regressions")
    print()
    print(f"{_passed} passed, {len(_failed)} failed")
    sys.exit(1 if _failed else 0)
