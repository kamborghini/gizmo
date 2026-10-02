"""Build and type-check the Shopify admin print extensions.

Each extension is bundled with esbuild exactly as the Shopify CLI bundles it,
and its compressed size checked against Shopify's 64 KB limit. Its source is
then type-checked with tsc against the @shopify/ui-extensions version it
declares, through the per-module shopify.d.ts the CLI generates, built here
in a temporary folder so the extension folders are not touched. esbuild does
not type-check and neither does the CLI, so a prop or API Shopify renamed in a
new version would otherwise surface only in the admin.

Needs the root node_modules (`npm ci`). Without them it says so and passes,
unless --require is given, as CI gives it.
"""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 64 * 1024
BIN = os.path.join(ROOT, "node_modules", ".bin")

TSCONFIG = {
    "compilerOptions": {
        "jsx": "react-jsx", "jsxImportSource": "preact",
        "target": "ES2022", "module": "ESNext", "moduleResolution": "Bundler",
        "allowJs": True, "checkJs": True, "noEmit": True, "strict": False,
        "skipLibCheck": True, "lib": ["ES2022", "DOM"], "types": [],
    },
    "include": ["src", "shopify.d.ts"],
}


def _extensions() -> list:
    """(folder, entry module, target) for every UI extension with source."""
    out = []
    base = os.path.join(ROOT, "extensions")
    for name in sorted(os.listdir(base)):
        toml = os.path.join(base, name, "shopify.extension.toml")
        if not os.path.isfile(toml):
            continue
        text = open(toml, encoding="utf-8").read()
        module = target = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("module") and "=" in line:
                module = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("target") and "=" in line:
                target = line.split("=", 1)[1].strip().strip('"')
        if module and target:
            out.append((name, module, target))
    return out


def main() -> int:
    require = "--require" in sys.argv
    esbuild, tsc = os.path.join(BIN, "esbuild"), os.path.join(BIN, "tsc")
    if not (os.path.exists(esbuild) and os.path.exists(tsc)):
        print("extensions: node_modules are not installed (npm ci), so nothing was built or checked")
        return 1 if require else 0
    bad = 0
    for name, module, target in _extensions():
        src_dir = os.path.join(ROOT, "extensions", name)
        entry = os.path.normpath(os.path.join(src_dir, module))
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "bundle.js")
            r = subprocess.run([esbuild, entry, "--bundle", "--format=esm", "--minify", "--target=es2020",
                                "--jsx=automatic", "--jsx-import-source=preact", "--outfile=" + out,
                                "--log-level=warning"], capture_output=True, text=True, cwd=ROOT)
            if r.returncode:
                print(name + ": does not build\n" + r.stderr[:1500])
                bad += 1
                continue
            size = len(gzip.compress(open(out, "rb").read(), 9))
            print("%s: builds, %d bytes compressed (limit %d)" % (name, size, LIMIT))
            if size > LIMIT:
                bad += 1
            # The type check runs on a copy of the source beside the CLI-style
            # declaration, resolving packages from the root node_modules.
            check = os.path.join(tmp, "check")
            shutil.copytree(os.path.join(src_dir, "src"), os.path.join(check, "src"))
            os.symlink(os.path.join(ROOT, "node_modules"), os.path.join(check, "node_modules"))
            rel = "./" + os.path.relpath(entry, src_dir).replace(os.sep, "/")
            with open(os.path.join(check, "shopify.d.ts"), "w", encoding="utf-8") as fh:
                fh.write("import '@shopify/ui-extensions';\n\n//@ts-ignore\ndeclare module '%s' {\n"
                         "  const shopify: import('@shopify/ui-extensions/%s').Api;\n"
                         "  const globalThis: { shopify: typeof shopify };\n}\n" % (rel, target))
            with open(os.path.join(check, "tsconfig.json"), "w", encoding="utf-8") as fh:
                json.dump(TSCONFIG, fh)
            t = subprocess.run([tsc, "-p", "tsconfig.json", "--pretty", "false"],
                               capture_output=True, text=True, cwd=check)
            if t.returncode:
                print(name + ": type errors against " + target + "\n" + (t.stdout + t.stderr)[:3000])
                bad += 1
            else:
                print(name + ": types check against " + target)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
