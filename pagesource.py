"""The page, joined from its sections.

static/src/ holds the page as a shell and its stylesheet's and script's
sections, in the order static/src/manifest.json gives. The server joins them
at start-up into the one page it has always served (copilot._page_parts), and
the test suites read the page from here too, so nothing opens a page file of
its own. tests/browser/page-source.js is the same join in JavaScript.

    python pagesource.py --sha256   # the joined page's fingerprint
    python pagesource.py            # the joined page itself

Zero dependencies, like tokenvault.py.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join("static", "src")
CSS_MARK = "<!-- @css -->\n"
JS_MARK = "<!-- @js -->\n"


def manifest(root=ROOT):
    with open(os.path.join(root, SRC, "manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _read(root, rel):
    # newline="" keeps every byte as written: the join must be the file it replaced.
    with open(os.path.join(root, SRC, rel), encoding="utf-8", newline="") as fh:
        return fh.read()


def join(root=ROOT):
    m = manifest(root)
    lines = _read(root, m["shell"]).splitlines(keepends=True)
    # Each marker is a whole line of its own, exactly: an indented or doubled
    # one would leave a section with nowhere to go.
    at_css = [i for i, line in enumerate(lines) if line == CSS_MARK]
    at_js = [i for i, line in enumerate(lines) if line == JS_MARK]
    if len(at_css) != 1 or len(at_js) != 1 or at_css[0] > at_js[0]:
        raise ValueError("static/src/shell.html must hold the line %r and then the line %r, once each"
                         % (CSS_MARK.strip(), JS_MARK.strip()))
    c, j = at_css[0], at_js[0]
    return ("".join(lines[:c]) + "".join(_read(root, p) for p in m["css"]) + "".join(lines[c + 1:j])
            + "".join(_read(root, p) for p in m["js"]) + "".join(lines[j + 1:]))


def sha256(root=ROOT):
    return hashlib.sha256(join(root).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    if "--sha256" in sys.argv[1:]:
        print(sha256())
    else:
        sys.stdout.write(join())
