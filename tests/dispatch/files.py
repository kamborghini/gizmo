# =========================== files: the R2 file store =======================
class FakeS3:
    """Stands in for the boto3 client. Objects are a dict of key -> size."""
    def __init__(self):
        self.objects = {}
        self.cors = None
        self.bucket_exists = False
        self.fail = None
        self.calls = []
    def _guard(self, name):
        self.calls.append(name)
        if self.fail:
            raise RuntimeError(self.fail)
    def head_bucket(self, Bucket):
        self._guard("head_bucket")
        if not self.bucket_exists:
            raise RuntimeError("404 no bucket")
    def create_bucket(self, Bucket):
        self._guard("create_bucket")
        self.bucket_exists = True
    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self._guard("put_bucket_cors")
        self.cors = CORSConfiguration
    def generate_presigned_url(self, op, Params, ExpiresIn):
        self._guard("presign_" + op)
        self.presigns = getattr(self, "presigns", [])
        self.presigns.append(Params)
        return f"https://fake-r2.test/{Params['Key']}?op={op}&exp={ExpiresIn}"
    def _size(self, Key):
        # Older tests store a size; the mail tests store the actual bytes,
        # because a message has to be BUILT out of them.
        v = self.objects[Key]
        return len(v) if isinstance(v, (bytes, bytearray)) else int(v)
    def head_object(self, Bucket, Key):
        self._guard("head_object")
        if Key not in self.objects:
            raise RuntimeError("404 no object")
        return {"ContentLength": self._size(Key)}
    def get_object(self, Bucket, Key, Range=None):
        self._guard("get_object")
        import io, re
        if Key not in self.objects:
            raise KeyError(Key)
        v = self.objects[Key]
        if isinstance(v, (bytes, bytearray)):
            data = bytes(v)
        else:
            # A size-only object stands for a real upload of that name, so it
            # opens the way the real one would: the intake reads the first
            # bytes, and a .pdf that is all x's would be refused as a fake.
            ext = Key.rsplit(".", 1)[-1].lower() if "." in Key else ""
            magic = {"pdf": b"%PDF-1.4\n", "png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff\xe0",
                     "jpeg": b"\xff\xd8\xff\xe0", "gif": b"GIF89a", "webp": b"RIFF\x00\x00\x00\x00WEBP"}.get(ext, b"")
            data = (magic + b"x" * int(v))[:max(int(v), len(magic))]
        if Range:
            a, b = re.match(r"bytes=(\d+)-(\d+)", Range).groups()
            data = data[int(a):int(b) + 1]
        return {"Body": io.BytesIO(data), "ContentLength": len(data)}
    def delete_object(self, Bucket, Key):
        self._guard("delete_object")
        self.objects.pop(Key, None)
    def delete_objects(self, Bucket, Delete):
        # The reaper batches (1000 keys per call) so an R2 outage cannot hold
        # the files lock one round trip at a time. Per-key failures come back
        # in Errors, exactly as S3 reports them.
        self._guard("delete_objects")
        errors = []
        for o in (Delete or {}).get("Objects") or []:
            k = o.get("Key")
            if k in getattr(self, "undeletable", set()):
                errors.append({"Key": k, "Code": "AccessDenied"})
                continue
            self.objects.pop(k, None)
        return {"Errors": errors} if errors else {}
    def upload_fileobj(self, Fileobj, Bucket, Key):
        self._guard("upload_fileobj")
        data = Fileobj.read()
        self.objects[Key] = len(data)
        self.bodies = getattr(self, "bodies", {})
        self.bodies[Key] = data

def run_async(coro):
    """Run a coroutine without disturbing the loop the rest of the suite uses.
    asyncio.run() CLOSES the loop and leaves the thread without one, which
    breaks every test after it."""
    import asyncio as _a
    prev = _RUN_LOOP if _RUN_LOOP is not None and not _RUN_LOOP.is_closed() else None
    loop = _a.new_event_loop()
    _a.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        _a.set_event_loop(prev)


def with_files(fn, configured=True, s3=None):
    """Run fn(fake_s3) with the file store configured against a fake bucket."""
    fake = s3 or FakeS3()
    fileserver._files_mem = None
    saved = (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
             fileserver._files_s3_client, dict(fileserver._files_ready), fileserver.FILES_QUOTA_GB)
    if configured:
        fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY = "acct", "ak", "sk"
    else:
        fileserver.R2_ACCOUNT_ID = fileserver.R2_ACCESS_KEY_ID = fileserver.R2_SECRET_ACCESS_KEY = ""
    fileserver._files_s3_client = fake
    fileserver._files_ready.update({"bucket": False, "cors": False, "error": ""})
    try:
        os.remove(fileserver.FILES_PATH)
    except FileNotFoundError:
        pass
    try:
        fn(fake)
    finally:
        (fileserver.R2_ACCOUNT_ID, fileserver.R2_ACCESS_KEY_ID, fileserver.R2_SECRET_ACCESS_KEY,
         fileserver._files_s3_client, ready, fileserver.FILES_QUOTA_GB) = saved
        fileserver._files_ready.update(ready)
        fileserver._files_mem = None
        jsonstore._poisoned_stores.discard(fileserver.FILES_PATH)
        try:
            os.remove(fileserver.FILES_PATH)
        except FileNotFoundError:
            pass

@test
def t_files_routes_refuse_the_unauthenticated():
    def go(fake):
        for path in ("/api/files/tree", "/api/files/folder", "/api/files/upload-url",
                     "/api/files/complete", "/api/files/download-url", "/api/files/file"):
            r = client.post(path, json={})
            eq(r.status_code, 401, path + " without a session token")
    with_files(go)

@test
def t_files_folder_lifecycle():
    def go(fake):
        r = post("/api/files/folder", {"op": "add", "name": "Design"})
        eq(r.status_code, 200, r.text)
        fid = r.json()["id"]
        r2 = post("/api/files/folder", {"op": "add", "name": "design"})
        eq(r2.status_code, 400, "same name in the same place is refused, case blind")
        r3 = post("/api/files/folder", {"op": "add", "name": "2026", "parent_id": fid})
        eq(r3.status_code, 200, r3.text)
        child = r3.json()["id"]
        r4 = post("/api/files/folder", {"op": "delete", "id": fid})
        eq(r4.status_code, 400, "a folder holding a folder cannot be deleted")
        r5 = post("/api/files/folder", {"op": "rename", "id": child, "name": "Archive/2026"})
        eq(r5.status_code, 200)
        eq(r5.json()["store"]["folders"][child]["name"], "Archive_2026", "slashes cannot enter a name")
        eq(post("/api/files/folder", {"op": "delete", "id": child}).status_code, 200)
        eq(post("/api/files/folder", {"op": "delete", "id": fid}).status_code, 200, "empty now, deletable")
        r6 = post("/api/files/folder", {"op": "add", "name": "x", "parent_id": "d999"})
        eq(r6.status_code, 400, "a vanished parent is refused")
    with_files(go)

@test
def t_files_upload_flow_records_what_the_bucket_actually_holds():
    def go(fake):
        r = post("/api/files/upload-url", {"name": "artwork.pdf", "size": 10, "type": "application/pdf"})
        eq(r.status_code, 200, r.text)
        body = r.json()
        ok(body["url"].startswith("https://fake-r2.test/"), "a signed URL came back")
        eq(body["store"]["files"], {}, "a pending upload is not yet a file")
        # the browser lied about the size; the bucket knows the truth
        key = [c for c in [body["url"].split("?")[0].replace("https://fake-r2.test/", "")]][0]
        fake.objects[key] = 999
        r2 = post("/api/files/complete", {"id": body["id"]})
        eq(r2.status_code, 200, r2.text)
        f = r2.json()["store"]["files"][body["id"]]
        eq(f["size"], 999, "the recorded size is the bucket's, not the browser's claim")
        eq(f["status"], "active")
        ok(fake.cors is None or fake.cors, "cors configuration attempted only with an origin")
        r3 = post("/api/files/complete", {"id": body["id"]})
        eq(r3.status_code, 400, "completing twice is refused")
    with_files(go)

@test
def t_files_upload_guards():
    def go(fake):
        eq(post("/api/files/upload-url", {"name": "a", "size": 0}).status_code, 400, "empty file")
        eq(post("/api/files/upload-url", {"name": "a", "size": 5 * 1024 ** 4}).status_code, 400, "over the single-file cap")
        eq(post("/api/files/upload-url", {"name": "a", "size": 10, "folder_id": "d404"}).status_code, 400, "vanished folder")
        fileserver.FILES_QUOTA_GB = 0.0000001   # ~107 bytes
        r = post("/api/files/upload-url", {"name": "a", "size": 200})
        eq(r.status_code, 400, "quota")
        ok("storage space" in r.json()["error"], "the quota refusal says why")
    with_files(go)

@test
def t_files_unconfigured_says_so_plainly():
    def go(fake):
        r = post("/api/files/tree", {})
        eq(r.status_code, 200)
        eq(r.json()["store"]["configured"], False)
        r2 = post("/api/files/upload-url", {"name": "a.pdf", "size": 10})
        eq(r2.status_code, 400)
        ok("isn't connected yet" in r2.json()["error"], r2.text)
    with_files(go, configured=False)

@test
def t_files_complete_when_nothing_arrived():
    def go(fake):
        r = post("/api/files/upload-url", {"name": "a.pdf", "size": 10})
        eq(r.status_code, 200, r.text)
        r2 = post("/api/files/complete", {"id": r.json()["id"]})
        eq(r2.status_code, 400, "no object in the bucket means no file")
        ok("never arrived" in r2.json()["error"], r2.text)
    with_files(go)

@test
def t_files_trash_restore_and_the_vanished_folder():
    def go(fake):
        folder = post("/api/files/folder", {"op": "add", "name": "Jobs"}).json()["id"]
        up = post("/api/files/upload-url", {"name": "a.pdf", "size": 10, "folder_id": folder}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        r = post("/api/files/file", {"op": "trash", "id": up["id"]})
        eq(r.status_code, 200, r.text)
        st = r.json()["store"]
        eq(st["files"], {}, "a trashed file leaves the listing")
        eq(len(st["trash"]), 1, "and waits in the trash")
        eq(st["used"], 10, "but still occupies space until purged")
        eq(post("/api/files/folder", {"op": "delete", "id": folder}).status_code, 200,
           "a folder holding only trashed files can be deleted")
        r2 = post("/api/files/file", {"op": "restore", "id": up["id"]})
        eq(r2.status_code, 200, r2.text)
        f = r2.json()["store"]["files"][up["id"]]
        eq(f["folder_id"], "", "restored to the top level when its folder went away")
        eq(post("/api/files/file", {"op": "restore", "id": up["id"]}).status_code, 400,
           "restoring what is not in the trash is refused")
    with_files(go)

@test
def t_files_purge_is_the_only_deleter_of_bytes():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "old.pdf", "size": 10}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        post("/api/files/file", {"op": "trash", "id": up["id"]})
        up2 = post("/api/files/upload-url", {"name": "fresh.pdf", "size": 10}).json()
        key2 = up2["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key2] = 10
        post("/api/files/complete", {"id": up2["id"]})
        post("/api/files/file", {"op": "trash", "id": up2["id"]})
        d = fileserver._load_files()
        d["files"][up["id"]]["trashed_at"] = "2026-07-01T00:00:00+00:00"     # 31+ days ago
        fileserver._write_files(d)
        fileserver._files_tick()
        d2 = fileserver._load_files()
        ok(up["id"] not in d2["files"], "the old trash entry is gone")
        ok(key not in fake.objects, "and its bytes left the bucket")
        ok(up2["id"] in d2["files"], "fresh trash is untouched")
        ok(key2 in fake.objects, "and keeps its bytes")
    with_files(go)

@test
def t_files_abandoned_uploads_are_swept():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "ghost.pdf", "size": 10}).json()
        d = fileserver._load_files()
        d["files"][up["id"]]["created_at"] = "2026-08-10T00:00:00+00:00"     # days ago, never completed
        fileserver._write_files(d)
        fileserver._files_tick()
        ok(up["id"] not in fileserver._load_files()["files"], "a stale pending upload is dropped")
    with_files(go)

@test
def t_files_download_and_rename():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "a.pdf", "size": 10}).json()
        eq(post("/api/files/download-url", {"id": up["id"]}).status_code, 404,
           "a pending upload cannot be fetched")
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        r = post("/api/files/download-url", {"id": up["id"]})
        eq(r.status_code, 200, r.text)
        ok("op=get_object" in r.json()["url"], "a signed GET came back")
        r2 = post("/api/files/file", {"op": "rename", "id": up["id"], "name": "../../etc/passwd"})
        eq(r2.status_code, 200)
        name = r2.json()["store"]["files"][up["id"]]["name"]
        ok("/" not in name and not name.startswith("."), "a rename cannot climb paths: " + name)
        eq(fileserver._load_files()["files"][up["id"]]["r2_key"], key,
           "the bucket key never changes on rename")
    with_files(go)

@test
def t_files_presign_failure_is_a_plain_answer_not_a_500():
    def go(fake):
        fake.fail = "credentials rejected"
        r = post("/api/files/upload-url", {"name": "a.pdf", "size": 10})
        eq(r.status_code, 502, r.text)
        ok("Check the storage keys" in r.json()["error"] and "Railway" not in r.json()["error"], r.text)
        ok(fileserver._load_files()["files"] == {}, "no phantom record was kept")
    with_files(go)

@test
def t_files_corrupt_store_refuses_writes_and_keeps_the_file():
    def go(fake):
        with open(fileserver.FILES_PATH, "w") as fh:
            fh.write("{not json")
        fileserver._files_mem = None
        r = post("/api/files/tree", {})
        eq(r.status_code, 200, "reads survive a broken store")
        eq(r.json()["store"]["files"], {}, "as empty, never invented")
        r2 = post("/api/files/folder", {"op": "add", "name": "x"})
        eq(r2.status_code, 500, "writes are refused while the store is broken")
        eq(open(fileserver.FILES_PATH).read(), "{not json", "the broken file is preserved for repair")
    with_files(go)

@test
def t_files_storage_wobble_is_not_reported_as_a_lost_upload():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "a.pdf", "size": 10}).json()
        fake.fail = "gateway timeout"
        r = post("/api/files/complete", {"id": up["id"]})
        eq(r.status_code, 502, "a storage error is not 'never arrived'")
        ok("not lost" in r.json()["error"], r.text)
        fake.fail = None
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        eq(post("/api/files/complete", {"id": up["id"]}).status_code, 200,
           "the same upload completes once storage answers")
    with_files(go)

@test
def t_files_true_size_is_enforced_at_complete():
    def go(fake):
        fileserver.FILES_QUOTA_GB = 0.0000001   # ~107 bytes
        up = post("/api/files/upload-url", {"name": "liar.pdf", "size": 10}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 999              # claimed 10, sent 999
        r = post("/api/files/complete", {"id": up["id"]})
        eq(r.status_code, 400, "what landed is what counts, not what was claimed")
        ok("has not been kept" in r.json()["error"], r.text)
        r2 = post("/api/files/upload-url", {"name": "next.pdf", "size": 10})
        eq(r2.status_code, 400, "the refused upload still occupies space until swept")
    with_files(go)

@test
def t_files_pending_uploads_count_toward_the_space():
    def go(fake):
        fileserver.FILES_QUOTA_GB = 0.0000001   # ~107 bytes
        eq(post("/api/files/upload-url", {"name": "a", "size": 60}).status_code, 200)
        r = post("/api/files/upload-url", {"name": "b", "size": 60})
        eq(r.status_code, 400, "two in-flight uploads cannot share the same last bytes")
    with_files(go)

@test
def t_files_delete_now_frees_space_and_the_reaper_removes_the_bytes():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "old.pdf", "size": 10}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        post("/api/files/file", {"op": "trash", "id": up["id"]})
        r = post("/api/files/file", {"op": "destroy", "id": up["id"]})
        eq(r.status_code, 200, r.text)
        eq(r.json()["store"]["used"], 0, "the space frees at once")
        eq(r.json()["store"]["trash"], [], "and the trash entry is gone")
        ok(key in fake.objects, "bytes wait for the reaper, never a route")
        fileserver._files_tick()
        ok(key not in fake.objects, "the reaper removed the bytes")
        eq(fileserver._load_files()["doomed"], [], "and the doomed list is clear")
        up2 = post("/api/files/upload-url", {"name": "live.pdf", "size": 10}).json()
        k2 = up2["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[k2] = 10
        post("/api/files/complete", {"id": up2["id"]})
        eq(post("/api/files/file", {"op": "destroy", "id": up2["id"]}).status_code, 400,
           "an active file cannot be destroyed; it must pass through the trash")
    with_files(go)

@test
def t_files_a_failed_bucket_delete_is_retried_not_orphaned():
    def go(fake):
        up = post("/api/files/upload-url", {"name": "old.pdf", "size": 10}).json()
        key = up["url"].split("?")[0].replace("https://fake-r2.test/", "")
        fake.objects[key] = 10
        post("/api/files/complete", {"id": up["id"]})
        post("/api/files/file", {"op": "trash", "id": up["id"]})
        post("/api/files/file", {"op": "destroy", "id": up["id"]})
        fake.fail = "bucket unreachable"
        fileserver._files_tick()
        eq(fileserver._load_files()["doomed"], [key], "the key stays doomed when the delete fails")
        ok(key in fake.objects, "and the bytes are untouched")
        fake.fail = None
        fileserver._files_tick()
        ok(key not in fake.objects, "the next tick finishes the job")
        eq(fileserver._load_files()["doomed"], [], "and clears the list")
    with_files(go)

@test
def t_files_concurrent_uploads_do_not_clobber_the_store():
    # The browser runs three uploads at once. Each upload-url call awaits the
    # presign mid-way through its read-modify-write; without the store lock the
    # later write drops the earlier pending record and its complete() then 400s.
    # Raced on ONE loop through the real ASGI stack, exactly like production
    # (TestClient threads would each bring their own loop and distort the lock).
    def go(fake):
        import httpx
        async def race():
            gate._rl_hits.clear(); gate._rl_global.clear()
            transport = httpx.ASGITransport(app=server.mcp.streamable_http_app(**server.MCP_HTTP))
            headers = {"Authorization": "Bearer " + tok(), "X-App-Session": ensure_auth()}
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                         headers=headers) as ac:
                return await asyncio.gather(*[
                    ac.post("/api/files/upload-url", json={"name": f"f{n}.pdf", "size": 10})
                    for n in (1, 2, 3)])
        rs = run(race())
        for r in rs:
            eq(r.status_code, 200, r.text)
        ids = [r.json()["id"] for r in rs]
        eq(len(set(ids)), 3, "three distinct records")
        d = fileserver._load_files()
        for i in ids:
            ok(i in d["files"], f"record {i} survived the race")
    with_files(go)

@test
def t_files_r2_endpoint_is_allowed_by_the_page_csp():
    # The browser PUTs bytes straight to the bucket; a CSP that only knows
    # Shopify kills that transfer before it starts. Found live: every real
    # upload failed with "the transfer failed" while every server-side and
    # stubbed-browser check passed, because only a real browser enforces CSP.
    def go(fake):
        csp = client.get("/").headers.get("content-security-policy", "")
        connect = csp.split("connect-src", 1)[1].split(";")[0]
        ok("https://acct.r2.cloudflarestorage.com" in connect,
           "the account's R2 endpoint is in connect-src: " + connect)
    with_files(go)
    def go2(fake):
        csp = client.get("/").headers.get("content-security-policy", "")
        ok("r2.cloudflarestorage.com" not in csp,
           "an unconfigured app allows nothing extra")
    with_files(go2, configured=False)

@test
def t_files_disposition_and_names():
    eq(fileserver._files_clean_name("  ../we\x00ird/na me.pdf  "), "_we_ird_na me.pdf")
    eq(fileserver._files_clean_name(""), "untitled")
    eq(fileserver._files_clean_name("x" * 300), "x" * 180)
    d = fileserver._files_disposition('café "q".pdf')
    ok("filename*=UTF-8''caf%C3%A9" in d, d)
    ok('\n' not in d and '\r' not in d, "no header injection")

