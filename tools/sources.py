"""The files the server's code lives in, for the test suites and the tools.

copilot.py held all of it until stage 4 of the 14 October audit began moving
areas out into the gizmo package (dispatch first). A check that reads
copilot.py alone goes blind to code that has moved: it passes with nothing to
look at. So every check and tool reads the code through here, and nothing
else opens copilot.py by name (t_nothing_reads_copilot_py_by_name).

    COPILOT_FILES    copilot.py, then every module split out of it
    copilot_files()  the same under another checkout's root
    APP_MODULES      every module of the app, for the security scans
    copilot_source() the text of COPILOT_FILES, joined

Imports nothing from the app, like the reference tools that use it.
"""
import glob
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _package(root=ROOT):
    """The gizmo package's modules, repo-relative, in a fixed order."""
    found = glob.glob(os.path.join(root, "gizmo", "**", "*.py"), recursive=True)
    return sorted(os.path.relpath(p, root).replace(os.sep, "/") for p in found)


def copilot_files(root=ROOT):
    """copilot.py, then every module split out of it, under `root`."""
    return ["copilot.py"] + _package(root)


COPILOT_FILES = copilot_files()

APP_MODULES = ["server.py", "copilot.py", "pagesource.py", "perf.py",
               "google_mail.py", "google_data.py", "xero.py", "worldoptions.py",
               "recon.py", "mailmime.py", "eori.py", "pipedrive.py",
               "tokenvault.py", "logdrain.py", "totp.py"] + _package()


def copilot_source():
    """copilot.py and every module split out of it, as one text."""
    parts = []
    for rel in COPILOT_FILES:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            parts.append(fh.read())
    return "\n".join(parts)
