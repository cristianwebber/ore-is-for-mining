#!/usr/bin/env python3
"""Builds the release zip and (with --publish) uploads it to the Factorio mod portal.

usage:
  python3 tools/release.py                 # validate + build dist/<name>_<version>.zip
  python3 tools/release.py --publish       # ...and upload it

Publishing needs an API key from https://factorio.com/profile in FACTORIO_API_KEY with the
scopes "ModPortal: Upload Mods", "ModPortal: Publish Mods" (first release only) and
"ModPortal: Edit Mods" (to sync the description from README.md).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = "https://mods.factorio.com"

# Portal metadata. Category/tags/license values are the API's enum names.
CATEGORY = "tweaks"
TAGS = ["mining", "environment"]
LICENSE = "default_mit"

# Everything that goes into the zip; tests/, tools/, dist/ and docs stay out.
INCLUDE = ["info.json", "changelog.txt", "thumbnail.png", "LICENSE", "settings.lua", "data.lua",
           "data-final-fixes.lua", "locale"]


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def load_info():
    info = json.loads((ROOT / "info.json").read_text())
    for key in ("name", "version", "title", "author", "factorio_version"):
        if not info.get(key):
            die(f"info.json is missing {key}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", info["version"]):
        die(f"info.json version {info['version']!r} is not X.Y.Z")
    return info


def check_changelog(version):
    lines = (ROOT / "changelog.txt").read_text().splitlines()
    for i, line in enumerate(lines, 1):
        if line.startswith("-") and line != "-" * 99:
            die(f"changelog.txt:{i}: separator lines must be exactly 99 dashes")
        if line.startswith("\t"):
            die(f"changelog.txt:{i}: tabs are not allowed, use spaces")
    versions = [l.split(":", 1)[1].strip() for l in lines if l.startswith("Version:")]
    if not versions or versions[0] != version:
        die(f"the first changelog.txt entry must be Version: {version}")


def run_tests():
    print("Running tests...", flush=True)
    if subprocess.run([str(ROOT / "tests" / "run.sh")], cwd=ROOT).returncode != 0:
        die("tests failed")


def warn_if_dirty():
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return
    if out.strip():
        print("warning: uncommitted changes will be included in the release")


def build_zip(info):
    folder = f"{info['name']}_{info['version']}"
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    path = dist / f"{folder}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in INCLUDE:
            src = ROOT / entry
            if not src.exists():
                die(f"missing {entry}")
            files = [src] if src.is_file() else sorted(p for p in src.rglob("*") if p.is_file())
            for f in files:
                zf.write(f, f"{folder}/{f.relative_to(ROOT).as_posix()}")
    print(f"Built {path.relative_to(ROOT)}")
    return path


# --- Portal API --------------------------------------------------------------

def request(url, fields=None, files=None, api_key=None, method="POST"):
    boundary = uuid.uuid4().hex
    body = b""
    for name, value in (fields or []):
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                 f"{value}\r\n").encode()
    for name, path, content_type in (files or []):
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                 f"filename=\"{path.name}\"\r\nContent-Type: {content_type}\r\n\r\n").encode()
        body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}",
               "User-Agent": "ore-is-for-mining-release"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body if method == "POST" else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read())
        except ValueError:
            payload = {}
        die(f"{url} -> HTTP {e.code}: {payload.get('error', '')} {payload.get('message', '')}".strip())


def portal_releases(name):
    """Returns the list of released versions, or None if the mod isn't on the portal yet."""
    try:
        with urllib.request.urlopen(f"{PORTAL}/api/mods/{name}") as resp:
            return [r["version"] for r in json.loads(resp.read()).get("releases", [])]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        die(f"could not query the mod portal: HTTP {e.code}")


def check_ok(result, step):
    if result.get("error"):
        die(f"{step} failed: {result['error']} {result.get('message', '')}")
    return result


def publish(info, zip_path):
    api_key = os.environ.get("FACTORIO_API_KEY")
    if not api_key:
        die("set FACTORIO_API_KEY (create one at https://factorio.com/profile)")
    name = info["name"]
    description = (ROOT / "README.md").read_text()
    releases = portal_releases(name)

    if releases is None:
        print(f"{name} is not on the portal yet, publishing it as a new mod...")
        init = check_ok(request(f"{PORTAL}/api/v2/mods/init_publish", [("mod", name)],
                                api_key=api_key), "init_publish")
        check_ok(request(init["upload_url"],
                         [("description", description), ("category", CATEGORY),
                          ("license", LICENSE)],
                         [("file", zip_path, "application/zip")]), "upload")
    else:
        if info["version"] in releases:
            die(f"version {info['version']} is already on the portal; bump info.json")
        print(f"Uploading {name} {info['version']}...")
        init = check_ok(request(f"{PORTAL}/api/v2/mods/releases/init_upload", [("mod", name)],
                                api_key=api_key), "init_upload")
        check_ok(request(init["upload_url"], files=[("file", zip_path, "application/zip")]),
                 "upload")

    print("Syncing title, summary, description and tags...")
    fields = [("mod", name), ("title", info["title"]), ("summary", info.get("description", "")),
              ("description", description), ("category", CATEGORY), ("license", LICENSE)]
    if info.get("homepage"):
        fields += [("homepage", info["homepage"]), ("source_url", info["homepage"])]
    fields += [("tags", t) for t in TAGS]
    check_ok(request(f"{PORTAL}/api/v2/mods/edit_details", fields, api_key=api_key),
             "edit_details")
    print(f"Done: {PORTAL}/mod/{name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--publish", action="store_true", help="upload to the mod portal")
    parser.add_argument("--skip-tests", action="store_true", help="don't run tests/run.sh")
    args = parser.parse_args()

    info = load_info()
    check_changelog(info["version"])
    if len(info.get("description", "")) > 500:
        die("info.json description is longer than the portal's 500-character summary limit")
    if not args.skip_tests:
        run_tests()
    warn_if_dirty()
    zip_path = build_zip(info)
    if args.publish:
        publish(info, zip_path)
    else:
        print("Dry run: nothing uploaded. Re-run with --publish to release.")


if __name__ == "__main__":
    main()
