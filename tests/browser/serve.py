"""Serve the real app for the browser suite, inside the dispatch suite's own world.

The dispatch suite's setup (every line of tests/test_dispatch.py before its
first test) gives the app scratch stores, a fake Shopify, invented accounts
and a network block. The seed then fills every screen through the app's own
code (tests/browser/seed/). The app is then served exactly as `make run`
serves it: server.build_app() under uvicorn.

    python tests/browser/serve.py      # PORT (8930); writes tests/browser/.run/auth.json

The local design rig has run the app this way since September.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RUN = os.environ.get("BROWSER_RUN") or os.path.join(HERE, ".run")
MARK = "\n@test\n"


def prelude_source_from(text):
    """The setup part of the dispatch suite, or a refusal naming the marker."""
    if MARK not in text:
        raise SystemExit("serve.py: tests/test_dispatch.py has no line '@test' after its setup, so the "
                         "setup cannot be found; the world would be half built, so nothing is served")
    src = text[:text.index(MARK)]
    tests = os.path.join(ROOT, "tests")
    src = src.replace("os.path.dirname(os.path.dirname(os.path.abspath(__file__)))", repr(ROOT))
    src = src.replace("os.path.dirname(os.path.abspath(__file__))", repr(tests))
    src = src.replace("os.path.dirname(__file__)", repr(tests))
    # No App Bridge in a plain browser: the page takes window.shopify from the suite.
    src = src.replace("\nimport jwt\n", "\nos.environ.pop('SHOPIFY_API_KEY', None)\nimport jwt\n", 1)
    return src


def build_world():
    os.chdir(ROOT)
    sys.path.insert(0, ROOT)
    sys.path.insert(0, HERE)
    os.environ["RATE_LIMIT_PER_CLIENT"] = "100000"
    os.environ["FORECAST_INGEST_TOKEN"] = "browser-suite-forecast-token-0123456789"
    text = open(os.path.join(ROOT, "tests", "test_dispatch.py"), encoding="utf-8").read()
    g = {"__name__": "browser_world", "__file__": os.path.join(ROOT, "tests", "test_dispatch.py")}
    exec(compile(prelude_source_from(text), "tests/test_dispatch.py (setup)", "exec"), g)
    g["ensure_auth"]()
    from seed import seed
    g["SEEDED"] = seed(g)
    return g


def main():
    import jwt
    import uvicorn
    port = int(os.environ.get("PORT", "8930"))
    g = build_world()
    now = int(time.time())
    token = jwt.encode({"iss": "https://test-store.myshopify.com/admin", "dest": "https://test-store.myshopify.com",
                        "aud": "a", "exp": now + 6 * 3600, "nbf": now - 5}, g["SECRET"], algorithm="HS256")
    os.makedirs(RUN, exist_ok=True)
    auth = {"base": f"http://127.0.0.1:{port}", "token": token, "session": g["APP_AUTH"]["session"],
            "master": g["APP_AUTH"]["master"], "localStorage": g["SEEDED"]["localStorage"]}
    with open(os.path.join(RUN, "auth.json"), "w", encoding="utf-8") as fh:
        json.dump(auth, fh)
    print(f"browser world ready on {auth['base']}", flush=True)
    uvicorn.run(g["server"].build_app(), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
