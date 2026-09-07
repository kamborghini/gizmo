"""Refuse a tree that carries a credential or an invisible character.

Run by CI on every push. Zero dependencies on purpose: the sweep that guards
the supply chain should not itself be a package. Placeholders in README and
env.example (shpat_xxxx...) are the documented shape and are allowed.
"""
import re
import subprocess
import sys

SECRETS = [
    re.compile(r"\b(shpat|shpca|shpss|shppa)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(ant-)?[A-Za-z0-9_\-]{24,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}"),
    re.compile(r"\b1//0[A-Za-z0-9_\-]{20,}"),
    re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY-----"),
]
# The tests carry fake credentials on purpose - the vault test needs a value
# shaped like a Google refresh token to prove it gets sealed. Naming the exact
# fixtures is the difference between "the tests are exempt" (which is where a
# real key pasted into a test would have lived, unnoticed, in an 800KB file)
# and "these four strings are known and everything else is a finding".
# Written in halves so this file does not trip its own scan - which is also
# the proof that the scan reads it like any other file.
_G = "1//"
TEST_FIXTURES = {
    _G + "0gRefreshTokenThatWouldReadAMailbox",
    _G + "0gTheRealRefreshToken",
    _G + "0gSecretValueHere",
    _G + "refresh-token",
}
INVISIBLE = re.compile("[\u061c\u200b-\u200f\u202a-\u202e\u2066-\u2069\u2028\u2029\ufeff]")
TEXT = (".py", ".js", ".html", ".yml", ".yaml", ".toml", ".md", ".txt", ".csv", ".json", ".css")

files = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
bad = 0
for f in files:
    if not f.endswith(TEXT):
        continue
    try:
        text = open(f, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        continue
    for i, line in enumerate(text.splitlines(), 1):
        # A byte-order mark opening a spreadsheet export is Excel's doing and
        # says nothing about the tree; anywhere else an invisible is a finding.
        probe = line[1:] if (i == 1 and f.endswith(".csv") and line[:1] == "\ufeff") else line
        if INVISIBLE.search(probe):
            print(f"{f}:{i}: invisible or bidirectional character"); bad += 1
        for pat in SECRETS:
            m = pat.search(line)
            if m and f.startswith("tests/") and m.group(0) in TEST_FIXTURES:
                continue
            if m and not re.fullmatch(r"[A-Za-z_]+x{10,}", m.group(0).split("_", 1)[-1] if "_" in m.group(0) else ""):
                print(f"{f}:{i}: looks like a credential ({pat.pattern[:24]}...)"); bad += 1
if bad:
    print(f"{bad} problem(s)"); sys.exit(1)
print("tree is clean")
