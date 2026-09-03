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
        if f.startswith("tests/"):
            continue        # the tests carry fake tokens on purpose; the vault test needs one
        for pat in SECRETS:
            m = pat.search(line)
            if m and not re.fullmatch(r"[A-Za-z_]+x{10,}", m.group(0).split("_", 1)[-1] if "_" in m.group(0) else ""):
                print(f"{f}:{i}: looks like a credential ({pat.pattern[:24]}...)"); bad += 1
if bad:
    print(f"{bad} problem(s)"); sys.exit(1)
print("tree is clean")
