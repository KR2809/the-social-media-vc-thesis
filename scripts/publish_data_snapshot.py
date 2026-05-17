"""Publish a versioned data snapshot as a GitHub release artifact.

DECISION_LOG iter-13: the second reproducibility path (alongside live
Supabase + local-clone re-run). Examiners cite a specific snapshot
version + download the tar.gz from the GitHub release page to verify
every number in the thesis.

What this script does:

  1. Walks `data/processed/` and selected `data/interim/` files.
  2. Computes SHA-256 of each file; writes a manifest JSON.
  3. tar.gz the whole bundle plus the manifest.
  4. Creates / updates a GitHub release tagged with the snapshot
     version. Uploads the tar.gz as a release asset.
  5. Inserts a row into Supabase `snapshots` table with the
     manifest's overall sha256, release URL, file count + bytes.

The snapshot version is computed deterministically from the current
git HEAD commit + ISO date — so the same commit + date always
produces the same version string, and re-running produces a no-op
if the artifact is already attached.

This is intentionally NOT integrated into pipeline.py — snapshots
are manually published when the data state is meant to be a citable
reference (e.g. v1.0-thesis-submission on May 31).

Usage:
    # Inspect what would be published, don't push:
    python -m scripts.publish_data_snapshot --dry-run

    # Publish to GitHub release:
    python -m scripts.publish_data_snapshot --tag v1.0-thesis-submission

    # Skip Supabase row insert (just GitHub):
    python -m scripts.publish_data_snapshot --tag latest --skip-supabase
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("publish_data_snapshot")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROCESSED = _REPO_ROOT / "data" / "processed"
_INTERIM = _REPO_ROOT / "data" / "interim"
_OUT_DIR = _REPO_ROOT / "data" / "snapshots"

# Files to include in the snapshot. Glob patterns relative to repo root.
_INCLUDE_PATTERNS = [
    "data/processed/*.parquet",
    "data/processed/*.csv",
    "data/processed/*.graphml",
    "data/interim/signal_events.parquet",
    "data/interim/topic_momentum.parquet",
    "data/interim/llm_run_log.jsonl",
]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
            cwd=_REPO_ROOT,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _git_dirty() -> bool:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], check=True, capture_output=True, text=True,
            cwd=_REPO_ROOT,
        )
        return bool(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return True


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_files() -> list[Path]:
    found: list[Path] = []
    for pat in _INCLUDE_PATTERNS:
        for p in _REPO_ROOT.glob(pat):
            if p.is_file():
                found.append(p)
    return sorted(set(found))


def _default_snapshot_version() -> str:
    """Deterministic version derived from commit + date.

    Two snapshots taken on the same day from the same commit produce
    the same version → safe re-run / re-publish becomes a no-op.
    """
    today = datetime.now(UTC).date().isoformat()
    sha = _git_commit()
    short = sha[:7] if sha != "unknown" else "nogit"
    return f"snap-{today}-{short}"


def build_snapshot(
    out_dir: Path = _OUT_DIR,
    version: str | None = None,
    fail_if_dirty: bool = False,
) -> tuple[Path, dict]:
    """Produce the local tar.gz + manifest. Returns (tar_path, manifest)."""
    if fail_if_dirty and _git_dirty():
        raise RuntimeError(
            "git working tree is dirty — commit or stash first, or pass "
            "--allow-dirty (defaults to allowed)."
        )

    version = version or _default_snapshot_version()
    out_dir.mkdir(parents=True, exist_ok=True)
    files = _collect_files()
    if not files:
        raise RuntimeError("no files matched the include patterns; nothing to publish")

    manifest = {
        "snapshot_version": version,
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "files": [],
    }
    for f in files:
        rel = str(f.relative_to(_REPO_ROOT))
        sha = _sha256_file(f)
        size = f.stat().st_size
        manifest["files"].append({"path": rel, "sha256": sha, "bytes": size})
    manifest["file_count"] = len(files)
    manifest["total_bytes"] = sum(e["bytes"] for e in manifest["files"])
    manifest_sha = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest["manifest_sha256"] = manifest_sha

    # Write manifest as a sibling JSON file for human inspection.
    manifest_path = out_dir / f"{version}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Build the tar.gz containing files + manifest.
    tar_path = out_dir / f"{version}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for f in files:
            tar.add(f, arcname=str(f.relative_to(_REPO_ROOT)))
        tar.add(manifest_path, arcname="manifest.json")

    print(
        f"snapshot | version={version} | files={len(files)} | "
        f"bytes={manifest['total_bytes']:,} | "
        f"manifest_sha256={manifest_sha[:12]}…"
    )
    print(f"snapshot | tarball: {tar_path}")
    return tar_path, manifest


def publish_to_github(
    tag: str,
    tar_path: Path,
    manifest: dict,
    notes: str | None = None,
) -> str:
    """Create / update a GitHub release with the snapshot attached.

    Requires `gh` CLI to be authenticated. Returns the release URL.
    """
    # Check if release already exists; if so, upload as a new asset (overwriting).
    notes = notes or (
        f"Data snapshot for thesis reproducibility. DECISION_LOG iter-13.\n\n"
        f"- version: {manifest['snapshot_version']}\n"
        f"- git_commit: {manifest['git_commit']}\n"
        f"- file_count: {manifest['file_count']}\n"
        f"- total_bytes: {manifest['total_bytes']:,}\n"
        f"- manifest_sha256: `{manifest['manifest_sha256']}`\n"
    )
    exists = subprocess.run(
        ["gh", "release", "view", tag],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    if exists.returncode == 0:
        # Upload as additional asset (clobber if same name).
        subprocess.run(
            ["gh", "release", "upload", tag, str(tar_path), "--clobber"],
            check=True, cwd=_REPO_ROOT,
        )
        print(f"snapshot | uploaded asset to existing release {tag}")
    else:
        subprocess.run(
            [
                "gh", "release", "create", tag, str(tar_path),
                "--title", f"Data snapshot {tag}",
                "--notes", notes,
            ],
            check=True, cwd=_REPO_ROOT,
        )
        print(f"snapshot | created release {tag}")

    # Build the URL.
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "url", "-q", ".url"],
        check=True, capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    repo_url = out.stdout.strip()
    return f"{repo_url}/releases/tag/{tag}"


def record_snapshot_in_supabase(
    manifest: dict,
    github_release_url: str | None,
) -> None:
    """Insert one row into Supabase `snapshots` table."""
    load_dotenv(override=True)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        logger.warning(
            "Supabase credentials missing — skipping snapshot row insert. "
            "Set SUPABASE_SERVICE_ROLE_KEY in .env to enable."
        )
        return
    from supabase import create_client  # noqa: PLC0415

    client = create_client(url, key)
    row = {
        "snapshot_version": manifest["snapshot_version"],
        "git_commit": manifest["git_commit"],
        "github_release_url": github_release_url,
        "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "sha256_manifest": manifest["manifest_sha256"],
    }
    client.table("snapshots").upsert(row, on_conflict="snapshot_version").execute()
    print(f"snapshot | recorded in Supabase snapshots table ({manifest['snapshot_version']})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish a data snapshot.")
    ap.add_argument("--tag", type=str, default=None, help="GitHub release tag.")
    ap.add_argument("--version", type=str, default=None, help="Override snapshot version.")
    ap.add_argument("--dry-run", action="store_true", help="Build tarball; skip upload.")
    ap.add_argument("--skip-github", action="store_true", help="Skip GitHub release upload.")
    ap.add_argument("--skip-supabase", action="store_true", help="Skip Supabase row insert.")
    ap.add_argument("--allow-dirty", action="store_true", default=True)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    tar_path, manifest = build_snapshot(
        version=args.version,
        fail_if_dirty=not args.allow_dirty,
    )

    if args.dry_run:
        print("snapshot | dry-run: built locally, no uploads")
        return 0

    github_url: str | None = None
    if not args.skip_github:
        tag = args.tag or manifest["snapshot_version"]
        github_url = publish_to_github(tag, tar_path, manifest)
        print(f"snapshot | github release URL: {github_url}")

    if not args.skip_supabase:
        record_snapshot_in_supabase(manifest, github_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
