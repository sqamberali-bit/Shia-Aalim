#!/usr/bin/env python3
"""Manage the external (out-of-git) knowledge corpus.

The built corpus lives outside version control (see docs/data-management.md).
This tool is how you get it onto a fresh checkout, verify it, and package it.

    python scripts/fetch_data.py --status                 # what's present vs the manifest
    python scripts/fetch_data.py --make-bundle            # tar+hash the local corpus
    python scripts/fetch_data.py --from-bundle <url|path> # download/verify/extract a bundle

To (re)build the GitHub-sourced works from scratch instead of fetching a bundle,
clone the source repos and run scripts/ingest.py (see docs/data-management.md).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE = ROOT / "data" / "knowledge"
MANIFEST = ROOT / "data" / "manifest.yaml"
BUNDLES = ROOT / "data" / "bundles"


def _load_manifest() -> dict:
    try:
        import yaml  # type: ignore
    except ImportError:
        sys.exit("PyYAML is required for this script: pip install pyyaml")
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def cmd_status(manifest: dict) -> int:
    print(f"Corpus manifest v{manifest.get('version')} — "
          f"expected {manifest.get('total_expected_docs')} docs\n")
    grand = 0
    missing = 0
    for work in manifest.get("works", []):
        pattern = work["output"].replace("data/knowledge/", "")
        files = sorted(KNOWLEDGE.glob(pattern))
        docs = sum(_count_lines(f) for f in files)
        grand += docs
        exp = work.get("expected_docs")
        if not files:
            missing += 1
            state = "MISSING"
        elif exp is not None and docs != exp:
            state = f"DRIFT (have {docs}, expect {exp})"
        else:
            state = "ok"
        print(f"  [{state:>22}] {work['id']:<26} {docs:>6} docs  ({work.get('tier')})")
    print(f"\n  total present: {grand} docs; {missing} work(s) missing.")
    if not any(KNOWLEDGE.glob("**/*.jsonl")):
        print("\n  No corpus found. Rebuild with scripts/ingest.py or fetch a bundle "
              "(--from-bundle). The committed sample is at data/knowledge/sample/.")
    return 0


def _iter_corpus_files() -> list[Path]:
    return sorted(p for p in KNOWLEDGE.glob("**/*.jsonl") if p.parent.name != "sample")


def cmd_make_bundle(out: str | None) -> int:
    files = _iter_corpus_files()
    if not files:
        sys.exit("No corpus files to bundle (only the sample is present).")
    BUNDLES.mkdir(parents=True, exist_ok=True)
    dest = Path(out) if out else BUNDLES / "shia-aalim-corpus.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        for f in files:
            tar.add(f, arcname=str(f.relative_to(ROOT)))
    digest = _sha256(dest)
    size = dest.stat().st_size
    print(f"Wrote {dest} ({size/1024/1024:.1f} MB, {len(files)} files)")
    print(f"sha256: {digest}")
    print("\nRecord these in data/manifest.yaml under `bundle:` after hosting the file.")
    return 0


def cmd_from_bundle(src: str, sha256: str | None, manifest: dict) -> int:
    expected = sha256 or (manifest.get("bundle") or {}).get("sha256")
    tmp = BUNDLES / "_download.tar.gz"
    BUNDLES.mkdir(parents=True, exist_ok=True)

    if src.startswith(("http://", "https://")):
        print(f"Downloading {src} ...")
        try:
            with urllib.request.urlopen(src, timeout=120) as resp:  # noqa: S310
                tmp.write_bytes(resp.read())
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"Download failed: {exc}\n(Only GitHub/allowed hosts are reachable here.)")
        archive = tmp
    else:
        archive = Path(src)
        if not archive.exists():
            sys.exit(f"No such file: {archive}")

    digest = _sha256(archive)
    if expected and digest != expected:
        sys.exit(f"Checksum mismatch!\n  expected {expected}\n  got      {digest}\n"
                 "Refusing to extract untrusted data.")
    if not expected:
        print(f"WARNING: no expected sha256 to verify against. Bundle sha256 is {digest}")

    with tarfile.open(archive, "r:*") as tar:
        _safe_extract(tar, ROOT)
    print(f"Extracted corpus into {KNOWLEDGE}. Run --status to verify.")
    return 0


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract, refusing any member that escapes the destination (tar traversal)."""
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            sys.exit(f"Unsafe path in archive: {member.name}")
    tar.extractall(dest)  # noqa: S202 - members validated above


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true", help="report present vs manifest")
    g.add_argument("--make-bundle", nargs="?", const=None, metavar="OUT",
                   help="tar+gzip the local corpus and print its sha256")
    g.add_argument("--from-bundle", metavar="URL_OR_PATH", help="fetch/verify/extract a bundle")
    parser.add_argument("--sha256", help="expected sha256 for --from-bundle")
    args = parser.parse_args()

    manifest = _load_manifest()
    if args.status:
        return cmd_status(manifest)
    if args.from_bundle:
        return cmd_from_bundle(args.from_bundle, args.sha256, manifest)
    return cmd_make_bundle(args.make_bundle)


if __name__ == "__main__":
    raise SystemExit(main())
