# ---- The app shell ----------------------------------------------------------

@test
def t_the_page_is_a_small_shell_and_the_bulk_is_cacheable():
    r = client.get("/")
    eq(r.status_code, 200, "the app loads")
    body = r.text
    ok(len(body) < 60000, "the shell is small: " + str(len(body)) + " bytes")
    ok("/assets/app.css?v=" in body, "the stylesheet moved to a hashed URL")
    ok("/assets/app.js?v=" in body, "and so did the script")
    ok("<style>" not in body and "<script>\n" not in body, "nothing bulky was left inline")
    urls = re.findall(r'/assets/app\.(?:css|js)\?v=[0-9a-f]+', body)
    ok(len(set(urls)) == 2, "the shell names both assets: " + str(set(urls)))
    css = client.get(sorted(set(urls))[0])
    js = client.get(sorted(set(urls))[1])
    eq(css.status_code, 200, "the stylesheet serves")
    eq(js.status_code, 200, "the script serves")
    # The page 404s outside the Shopify admin; the assets must not be a way round it.
    eq(client.get("/assets/app.js").status_code, 404, "no hash, no source")
    eq(client.get("/assets/app.js?v=deadbeef").status_code, 404, "and a wrong hash is no better")
    ok(len(css.text) > 20000 and len(js.text) > 100000, "and they carry the real weight")
    for res in (css, js):
        ok("immutable" in res.headers.get("cache-control", ""),
           "hashed assets cache for a year: " + res.headers.get("cache-control", ""))
    # The split must lose nothing: shell + css + js is the whole page again.
    whole = pagesource.join(HERE)
    eq(len(body) + len(css.text) + len(js.text) > len(whole) - 200, True,
       "the page was split, not truncated")

@test
def t_a_repeat_open_of_the_same_build_is_a_304_that_still_carries_the_csp():
    r = client.get("/")
    etag = r.headers.get("etag")
    ok(etag, "the shell is tagged with its build")
    again = client.get("/", headers={"If-None-Match": etag})
    eq(again.status_code, 304, "the same build is not sent twice")
    ok(again.headers.get("content-security-policy"), "and the 304 still pins frame-ancestors")
    ok("no-store" not in r.headers.get("cache-control", ""), "no-store would make the ETag inert")
    weak = client.get("/", headers={"If-None-Match": 'W/' + etag + ', "other"'})
    eq(weak.status_code, 304, "a weak tag in a list still matches")
    stale = client.get("/", headers={"If-None-Match": '"an-older-build"'})
    eq(stale.status_code, 200, "a different build is sent in full")

@test
def t_a_page_that_cannot_be_split_is_still_served_whole():
    # A future edit to index.html must never be able to take the app down.
    shell, css, js = rendering._split_page("<html><body>hello</body></html>")
    eq(css, "", "no stylesheet was invented")
    eq(js, "", "no script was invented")
    eq(shell, "<html><body>hello</body></html>", "and the page is served exactly as authored")

