#!/usr/bin/env python3
"""Refresh the committed KJV2006 USFX source, with safe fallback."""
from pathlib import Path
import hashlib, json, shutil, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/kjv2006/eng-kjv2006_usfx.xml"
URL = "https://ebible.org/Scriptures/eng-kjv2006_usfx.zip"
EXPECTED = "eng-kjv2006_usfx.xml"

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def validate(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Missing source: {path}")
    ET.parse(path)
    return sha256(path)

def refresh():
    work = ROOT / "build/source-refresh"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    archive = work / "source.zip"

    req = urllib.request.Request(URL, headers={"User-Agent": "BibleStudy/1.0"})
    with urllib.request.urlopen(req, timeout=180) as response:
        archive.write_bytes(response.read())

    extract = work / "extract"
    extract.mkdir()
    with zipfile.ZipFile(archive) as z:
        hits = [n for n in z.namelist() if Path(n).name == EXPECTED]
        if len(hits) != 1:
            raise RuntimeError(f"Expected exactly {EXPECTED}; found {hits}")
        z.extract(hits[0], extract)
        candidate = extract / hits[0]

    validate(candidate)
    SOURCE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate, SOURCE)

def main():
    mode = "committed"
    if "--refresh" in sys.argv:
        try:
            refresh()
            mode = "downloaded"
        except Exception as exc:
            if not SOURCE.exists():
                raise
            mode = f"committed-fallback: {exc}"

    digest = validate(SOURCE)
    out = ROOT / "build/source_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "source": EXPECTED,
        "url": URL,
        "sha256": digest,
        "acquisition": mode,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"source={SOURCE}")
    print(f"sha256={digest}")
    print(f"mode={mode}")

if __name__ == "__main__":
    main()
