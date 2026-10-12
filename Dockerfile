# Python 3.14 on Debian 13, pinned by digest so a build gets exactly the image
# that was tested. Dependabot (docker, below in .github/dependabot.yml) raises
# the digest when the image is rebuilt with Debian security fixes; moving to a
# new Python minor stays a deliberate change. 3.14.8 ships pip 26.2.1.
FROM python:3.14.8-slim-trixie@sha256:89fb7d3da20043c370643435258bdd7ab755d326d359001d02988ed15ae5219e

WORKDIR /app

COPY requirements.txt .
# requirements.txt is the hashed lock (`make lock`): every package, pinned, and
# refused if its download does not match.
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY . .

# Still root, and that is a KNOWN, ACCEPTED gap, not an oversight - do not
# "fix" it by adding USER without testing the volume first.
#
# The 2026-08-30 hardening audit raised the root process (it terminates
# untrusted HTTP, parses uploaded PDFs and writes every store). The fix is
# blocked by the platform: Railway's own docs say "Docker images that run as a
# non-root UID by default will have permissions issues when performing
# operations within an attached volume", and their documented answer is
# RAILWAY_RUN_UID=0 - which is root again. /data holds the dispatch records,
# so a container that cannot write it takes the dispatch desk down.
#
# The real fix is an entrypoint that starts as root, chowns the mounted volume,
# then drops privileges before exec'ing the app. That needs to be built and
# proven against a real volume mount before it ships. Until then this is a
# written risk acceptance: accepted by Cameron, revisit when the entrypoint can
# be tested on a scratch service.

EXPOSE 8000

CMD ["python", "server.py"]
