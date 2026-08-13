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


if __name__ == "__main__":
    print("frontend regressions")
    print()
    print(f"{_passed} passed, {len(_failed)} failed")
    sys.exit(1 if _failed else 0)
