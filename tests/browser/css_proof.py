"""make css-proof BASE=<ref>: prove a stylesheet change changed nothing.

The base is checked out in a worktree of its own and shot once on port 8942,
the working tree twice on 8941 (two runs give the noise of clocks and times),
each with the working tree's own probe (tests/browser/computed.js and
css-proof.spec.js, copied into the base so any base can be shot). Then
computed.js compares: a change is a style that differs from the base's in the
first head run and is the same in both. Exit 0 when no state changed.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOL = ("tests/browser/computed.js", "tests/browser/css-proof.spec.js")
BASE_PORT, HEAD_PORT = 8942, 8941


def shoot(tree, out, port, only):
    env = dict(os.environ, CSS_PROOF_OUT=out, BROWSER_PORT=str(port), BROWSER_RUN=out + "-run")
    if only:
        env["CSS_PROOF_ONLY"] = only
    r = subprocess.run(["npx", "playwright", "test", "-c", "tests/browser/playwright.config.js", "css-proof.spec.js",
                        "--reporter=line"], cwd=tree, env=env, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    print("  %s: %s" % (os.path.basename(out), last.strip()))
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="the ref to compare against")
    ap.add_argument("--only", help="a regular expression on <size>-<state>")
    ap.add_argument("--work", help="where the shots go (kept); a temporary folder otherwise")
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="css-proof-")
    os.makedirs(work, exist_ok=True)
    tree = os.path.join(work, "base")
    subprocess.run(["git", "worktree", "add", "-q", "--detach", tree, a.base], cwd=ROOT, check=True)
    try:
        for link in ("node_modules", ".venv"):
            os.symlink(os.path.join(ROOT, link), os.path.join(tree, link))
        for rel in TOOL:
            shutil.copy(os.path.join(ROOT, rel), os.path.join(tree, rel))
        print("shooting %s and the working tree in %s" % (a.base, work))
        shoot(tree, os.path.join(work, "base-out"), BASE_PORT, a.only)
        shoot(ROOT, os.path.join(work, "head1"), HEAD_PORT, a.only)
        shoot(ROOT, os.path.join(work, "head2"), HEAD_PORT, a.only)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", tree], cwd=ROOT)
    r = subprocess.run(["node", os.path.join(ROOT, "tests/browser/computed.js"), os.path.join(work, "base-out"),
                        os.path.join(work, "head1"), os.path.join(work, "head2")])
    if not a.work and r.returncode == 0:
        shutil.rmtree(work, ignore_errors=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
