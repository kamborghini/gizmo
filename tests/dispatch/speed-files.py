# =========================== speed: Files, instant actions =====================
# The fourth speed pull request (the 2026-10-12 audit, S9 and P2). Every upload
# saved and sent back the whole Files store twice, held the store's lock while
# storage answered, and the page redrew the whole folder after every file.

def _files_key(up):
    return up["url"].split("?")[0].replace("https://fake-r2.test/", "")


def _files_apply(store, delta):
    """What the page does with a delta answer (filesPatch in the page)."""
    for k, v in (delta.get("files") or {}).items():
        if v:
            store["files"][k] = v
        else:
            store["files"].pop(k, None)
    for k, v in (delta.get("folders") or {}).items():
        if v:
            store["folders"][k] = v
        else:
            store["folders"].pop(k, None)
    tr = delta.get("trash") or {}
    if tr:
        store["trash"] = [t for t in store["trash"] if t["id"] not in tr] + [v for v in tr.values() if v]
    if delta.get("used") is not None:
        store["used"] = delta["used"]
    if "setup_error" in delta:
        store["setup_error"] = delta["setup_error"]
    if delta.get("names"):
        store["names"] = delta["names"]


async def _files_wait_for(event, gate, secs=10.0):
    """Wait for a fake's call to begin, failing (and freeing it) rather than
    spinning for ever when a change means storage is never asked."""
    for _ in range(int(secs / 0.01)):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    gate.set()
    raise AssertionError("storage was never asked")


def _files_race(*calls):
    """Requests raced on ONE loop through the real ASGI stack, as production
    runs them (TestClient threads would each bring their own loop)."""
    import httpx

    async def race():
        gate._rl_hits.clear(); gate._rl_global.clear()
        transport = httpx.ASGITransport(app=server.mcp.streamable_http_app(**server.MCP_HTTP))
        headers = {"Authorization": "Bearer " + tok(), "X-App-Session": ensure_auth()}
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                     headers=headers, timeout=30) as ac:
            return await asyncio.gather(*[c(ac) for c in calls])
    return run(race())


@test
def t_an_unchanged_files_tree_is_not_sent_again():
    """Every visit to Files re-read the whole store (about 85 KB at 2,000
    files, four times that at 8,000) to find, most times, nothing new. The
    store now comes with a revision, a fingerprint of what was sent; the
    page sends it back and an unchanged store answers {same: true}. A page
    with no revision (one open from before this update) gets the store."""
    def go(fake):
        t = post("/api/files/tree", {}).json()
        ok(t.get("store") and t.get("rev"), "the store comes with its revision")
        eq(post("/api/files/tree", {"rev": t["rev"]}).json(), {"same": True, "rev": t["rev"]},
           "nothing changed, nothing sent")
        ok("store" in post("/api/files/tree", {}).json(), "an older page still gets the store")
        f = post("/api/files/folder", {"op": "add", "name": "Jobs"}).json()
        ok(f.get("store") and f.get("rev") and f["rev"] != t["rev"], "a change answers the store under a new revision")
        moved = post("/api/files/tree", {"rev": t["rev"]}).json()
        ok(moved.get("store") and moved["rev"] == f["rev"], "and the tree sends the store that moved, under that revision")
        ok("store" in post("/api/files/tree", {"rev": "not-a-revision"}).json(), "an unknown revision gets the store")
    with_files(go)


@test
def t_an_upload_answers_what_changed_when_the_page_asks():
    """Each upload answered the whole store twice, once to sign for it and once
    to confirm it (about 20 ms of the server's one thread and 170 KB per file
    at 2,000 files). A page that sends delta gets only what changed: the
    records, the trash and the space used. Patching its copy with them gives
    exactly the store the tree answers, through a replacement into the trash.
    Without delta the answers are the whole store, as before."""
    def go(fake):
        # Storage had failed when the page last read the store: its banner says
        # so, and the first upload that finds storage back must clear it.
        fileserver._files_ready.update({"error": "RuntimeError: an earlier outage", "at": 0.0})
        mine = post("/api/files/tree", {}).json()["store"]
        ok(mine["setup_error"], "the page's copy shows the earlier failure")
        mine["names"] = {}                     # read before a teammate was added
        nf = post("/api/files/folder", {"op": "add", "name": "Jobs", "delta": 1}).json()
        ok("store" not in nf and nf.get("id") and nf.get("delta"), "a new folder answers itself: %r" % nf)
        _files_apply(mine, nf["delta"])

        def upload(name, size):
            a = post("/api/files/upload-url", {"name": name, "size": size, "folder_id": nf["id"], "delta": 1}).json()
            ok("store" not in a and a.get("id") and a.get("url"), "signing answers the upload, not the store: %r" % list(a))
            _files_apply(mine, a["delta"])
            fake.objects[_files_key(a)] = size
            c = post("/api/files/complete", {"id": a["id"], "delta": 1})
            eq(c.status_code, 200, c.text)
            ok("store" not in c.json(), "and confirming answers what changed")
            _files_apply(mine, c.json()["delta"])
            return a, c.json()
        upload("proof.pdf", 10)
        upload("Proof.PDF", 12)                  # replaces the first, which goes to the trash
        upload("notes.pdf", 7)
        full = post("/api/files/tree", {}).json()["store"]
        in_order = lambda st: {**st, "trash": sorted(st["trash"], key=lambda t: t["id"])}
        eq(in_order(mine), in_order(full), "the patched copy is exactly the store, field for field")
        eq(len(full["trash"]), 1, "the replaced proof is in the trash")
        eq(full["setup_error"], "", "storage recovered, and the patched copy says so too")
        ok(mine["names"].get(full["files"][next(iter(full["files"]))]["by"]), "and it names the uploader")
        old = post("/api/files/upload-url", {"name": "old-page.pdf", "size": 5}).json()
        ok(old.get("store") is not None, "a page that does not ask still gets the whole store")
    with_files(go)


@test
def t_confirming_an_upload_does_not_hold_files_while_storage_answers():
    """Confirming an upload asks storage twice (what really landed and its
    first bytes) and held the store's lock across both, so every other change
    to Files and the Finder drive waited on storage, and a batch's uploads
    were confirmed one at a time. Storage is now asked outside the lock and
    the record checked again before it is kept."""
    import threading

    class SlowHead(FakeS3):
        def __init__(self):
            super().__init__()
            self.entered, self.gate = threading.Event(), threading.Event()

        def head_object(self, Bucket, Key):
            self.entered.set()
            self.gate.wait(3)
            return super().head_object(Bucket, Key)
    slow = SlowHead()

    def go(fake):
        up = post("/api/files/upload-url", {"name": "slow.pdf", "size": 10}).json()
        fake.objects[_files_key(up)] = 10
        order = []

        async def complete(ac):
            r = await ac.post("/api/files/complete", json={"id": up["id"]})
            order.append("complete")
            return r

        async def folder(ac):
            await _files_wait_for(fake.entered, fake.gate)
            r = await ac.post("/api/files/folder", json={"op": "add", "name": "Meanwhile"})
            order.append("folder")
            fake.gate.set()
            return r
        rc, rf = _files_race(complete, folder)
        eq(rc.status_code, 200, rc.text)
        eq(rf.status_code, 200, rf.text)
        eq(order, ["folder", "complete"], "a folder was made while storage was still answering")
        eq(fileserver._load_files()["files"][up["id"]]["status"], "active", "and the upload was still kept")
    with_files(go, s3=slow)


@test
def t_signing_an_upload_does_not_hold_files_while_storage_is_set_up():
    """The first upload after a deploy, or one a minute while storage is
    failing, sets the bucket up over the network before it signs. That ran
    under the store's lock, so everything else in Files waited on it. It now
    runs before the lock is taken."""
    import threading

    class SlowSetup(FakeS3):
        def __init__(self):
            super().__init__()
            self.entered, self.gate = threading.Event(), threading.Event()

        def head_bucket(self, Bucket):
            self.entered.set()
            self.gate.wait(3)
            return super().head_bucket(Bucket)
    slow = SlowSetup()

    def go(fake):
        order = []

        async def sign(ac):
            r = await ac.post("/api/files/upload-url", json={"name": "first.pdf", "size": 10})
            order.append("sign")
            return r

        async def folder(ac):
            await _files_wait_for(fake.entered, fake.gate)
            r = await ac.post("/api/files/folder", json={"op": "add", "name": "Meanwhile"})
            order.append("folder")
            fake.gate.set()
            return r
        rs, rf = _files_race(sign, folder)
        eq(rs.status_code, 200, rs.text)
        eq(rf.status_code, 200, rf.text)
        eq(order, ["folder", "sign"], "a folder was made while storage was being set up")
    with_files(go, s3=slow)


@test
def t_uploads_during_a_storage_retry_wait_for_its_answer():
    """Setting the bucket up moved out of the store's lock, and a retry after
    a failure stamped its start time before it asked storage, so uploads
    arriving during the retry read it as a failure a moment ago and were
    refused (502) while it was about to succeed. They now wait for its
    answer: three uploads at once after storage comes back all sign."""
    import threading

    class SlowBucket(FakeS3):
        def __init__(self):
            super().__init__()
            self.heads = 0

        def head_bucket(self, Bucket):
            self.heads += 1
            time.sleep(0.4)
            return super().head_bucket(Bucket)
    slow = SlowBucket()

    def go(fake):
        fake.bucket_exists = True
        fileserver._files_ready.update({"bucket": False, "cors": False,
                                     "error": "RuntimeError: an earlier outage", "at": time.time() - 120})

        def sign(n):
            return lambda ac: ac.post("/api/files/upload-url", json={"name": f"back{n}.pdf", "size": 10})
        rs = _files_race(sign(1), sign(2), sign(3))
        eq([r.status_code for r in rs], [200, 200, 200], [r.text[:120] for r in rs])
        eq(fake.heads, 1, "storage was asked once, and the others took its answer")
        eq(fileserver._files_ready["error"], "", "and the failure is cleared")
    with_files(go, s3=slow)


@test
def t_an_upload_holding_files_never_waits_on_a_storage_setup():
    """Re-check of the review fixes. An upload that passed the setup check
    while a failure was fresh, then queued for the store's lock, set the
    bucket up again once inside it: with another upload's retry under way
    it waited for that retry holding the lock, and every change to Files and
    the Finder drive waited with it. Signing under the lock now only signs;
    the setup happens before the lock is taken."""
    import threading

    def go(fake):
        fileserver._files_ready.update({"bucket": False, "cors": False,
                                     "error": "RuntimeError: an earlier outage", "at": time.time()})

        async def scenario(ac):
            await fileserver._files_lock.acquire()          # the hourly sweep holds the store
            sign = asyncio.ensure_future(ac.post("/api/files/upload-url", json={"name": "c.pdf", "size": 10}))
            await asyncio.sleep(0.3)                     # it passed the fresh failure and queued
            fileserver._files_ready["at"] = time.time() - 120   # the minute is up: another upload retries
            busy = threading.Thread(target=lambda: (fileserver._files_setup_lock.acquire(), time.sleep(1.5),
                                                    fileserver._files_setup_lock.release()))
            busy.start()
            await asyncio.sleep(0.05)
            fileserver._files_lock.release()
            await asyncio.sleep(0.05)
            t0 = time.monotonic()
            f = await ac.post("/api/files/folder", json={"op": "add", "name": "Meanwhile"})
            waited = time.monotonic() - t0
            c = await sign
            busy.join()
            return c, f, waited
        (c, f, waited), = _files_race(scenario)
        eq(f.status_code, 200, f.text)
        ok(waited < 0.5, "the folder did not wait on another upload's storage retry: %.2f s" % waited)
        eq(c.status_code, 502, "the upload that met a storage not yet set up is refused at once: " + c.text[:120])
    with_files(go)


@test
def t_while_storage_hangs_an_upload_is_refused_without_waiting_out_the_retry():
    """Re-check of the review fixes. With storage hanging, one retry of the
    setup takes up to a minute (short timeouts, but three tries of two
    calls), and every upload arriving meanwhile waited the whole of it for
    a refusal. A setup another caller is running is waited for only a few
    seconds; a quick recovery is still waited for and taken."""
    import threading

    class Hanging(FakeS3):
        def __init__(self):
            super().__init__()
            self.release = threading.Event()

        def head_bucket(self, Bucket):
            self.release.wait(3)
            raise RuntimeError("storage did not answer")

        def create_bucket(self, Bucket):
            raise RuntimeError("storage did not answer")
    hang = Hanging()

    def go(fake):
        fileserver._files_ready.update({"bucket": False, "cors": False,
                                     "error": "RuntimeError: an earlier outage", "at": time.time() - 120})
        saved = fileserver.FILES_SETUP_WAIT
        fileserver.FILES_SETUP_WAIT = 0.3
        took = {}

        def sign(n, delay):
            async def go_(ac):
                await asyncio.sleep(delay)
                t0 = time.monotonic()
                r = await ac.post("/api/files/upload-url", json={"name": f"h{n}.pdf", "size": 10})
                took[n] = time.monotonic() - t0
                if n == 2:
                    fake.release.set()
                return r
            return go_
        try:
            rs = _files_race(sign(1, 0), sign(2, 0.2))
        finally:
            fileserver.FILES_SETUP_WAIT = saved
        eq([r.status_code for r in rs], [502, 502], [r.text[:80] for r in rs])
        ok(took[2] < 1.0, "the second upload was refused without waiting out the retry: %.2f s" % took[2])
    with_files(go, s3=hang)


@test
def t_one_upload_confirmed_twice_at_once_is_one_file():
    """With storage asked outside the lock, two confirmations of one upload (a
    retry while the first is still answering) can both be in flight. The
    record is checked again under the lock: one is kept, the other is told
    the upload is no longer expected, and the space is counted once."""
    import threading

    class SlowHead(FakeS3):
        def __init__(self):
            super().__init__()
            self.n, self.gate = 0, threading.Event()

        def head_object(self, Bucket, Key):
            self.n += 1
            if self.n >= 2:
                self.gate.set()
            self.gate.wait(3)
            return super().head_object(Bucket, Key)
    slow = SlowHead()

    def go(fake):
        up = post("/api/files/upload-url", {"name": "twice.pdf", "size": 10}).json()
        fake.objects[_files_key(up)] = 10

        def complete(ac):
            return ac.post("/api/files/complete", json={"id": up["id"]})
        a, b = _files_race(complete, complete)
        eq(sorted([a.status_code, b.status_code]), [200, 400], (a.text, b.text))
        d = fileserver._load_files()
        eq([v["status"] for v in d["files"].values()], ["active"], "one file")
        eq(fileserver._files_usage(d), 10, "counted once")
    with_files(go, s3=slow)


@test
def t_no_hosting_or_setting_name_reaches_a_person_from_the_server():
    """House rule: what a person reads from the server (an error, a note, an
    OAuth page, an emailed alert, the activity log, a sweep's notes) is plain
    British English that never names the hosting (Railway), the code name
    (gizmo) or a setting by its variable name. On 12 Oct 2026 errors still said
    "Add PIPEDRIVE_API_TOKEN in Railway" and the like, so every string in the
    server's files is read here, not only the ones somebody remembered to
    check. Left out: docstrings, what goes to the log, the name a lookup
    reads (a bare NAME), and the doors only a machine or the log reads."""
    import ast
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    words = re.compile(r"\bRailway\b|\bgizmo\b|\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
    quiet = re.compile(r"(logger|logging|log)\.\w+|print|os\.environ\.\w+|os\.getenv|_env_num")
    # Naming the variable is the point where only the operator or a client reads it.
    machine = {("server.py", "_boot_report"),           # the boot log's list of what is off
               ("server.py", "_error"),                 # the MCP tools' answers, read by the model
               ("server.py", "__call__"),               # the /mcp lock, read by an MCP client
               ("copilot", "_verify_session_token")}     # its refusal is only logged
    # copilot.py and the modules split out of it are one place here ("copilot").
    not_words = {"gizmo-build|", "gizmo"}                # a hash seed and a MIME boundary
    bad = []

    def visit(node, name, fn, hush):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = node.name
        if isinstance(node, ast.Call) and quiet.fullmatch(ast.unparse(node.func)):
            hush = True
        kids = list(ast.iter_child_nodes(node))
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
            kids.remove(body[0])                         # a docstring
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and not hush
                and ("copilot" if name in COPILOT_FILES else name, fn) not in machine
                and node.value not in not_words
                and not re.fullmatch(r"[A-Z][A-Z0-9_]*", node.value) and words.search(node.value)):
            bad.append("%s:%d %s" % (name, node.lineno, node.value[:80]))
        for k in kids:
            visit(k, name, fn, hush)
    for name in COPILOT_FILES + ["server.py", "google_mail.py",
                                 "pipedrive.py", "tokenvault.py", "worldoptions.py", "eori.py"]:
        visit(ast.parse(open(os.path.join(root, name), encoding="utf-8").read()), name, "", False)
    ok(not bad, "%d strings a person reads name the hosting, the code name or a setting: %s"
       % (len(bad), "; ".join(bad[:8])))


