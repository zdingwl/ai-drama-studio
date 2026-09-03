#!/usr/bin/env python3
"""Safely migrate one real V2 project to canonical current TargetDialogue semantics.

This tool does not delete historical projection-level TargetDialogue rows.  It treats a row as
current only when BOTH its source fingerprint and canonical dialogue_group_id belong to the
current SourceDramaSnapshot.  ``--apply`` creates a SQLite backup first, rebuilds only current
TargetDialogue text through the existing production service, and verifies the resulting current
bundle.  Without ``--apply`` it is read-only and only reports current/history counts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from sqlalchemy import select

from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import DB_PATH, Project, get_session
from engine.app.target_dialogue_v1 import (
    TargetDialogue,
    generate_target_dialogue_text_v1,
    get_target_dialogue_v1,
)


class TargetDialogueMigrationError(RuntimeError):
    pass


def _canonical_source_keys(snapshot: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    for episode in snapshot.get("episodes") or []:
        if not isinstance(episode, Mapping):
            continue
        utterances = episode.get("source_dialogue_utterances")
        if not isinstance(utterances, list):
            raise TargetDialogueMigrationError(
                "current SourceDramaSnapshot is not canonical: source_dialogue_utterances missing"
            )
        for utterance in utterances:
            if not isinstance(utterance, Mapping):
                continue
            key = str(utterance.get("dialogue_group_id") or "").strip()
            if not key:
                raise TargetDialogueMigrationError("canonical utterance is missing dialogue_group_id")
            keys.append(key)

    if len(keys) != len(set(keys)):
        raise TargetDialogueMigrationError("current SourceDramaSnapshot contains duplicate dialogue_group_id")

    declared_count = int(snapshot.get("source_dialogue_count") or 0)
    if declared_count != len(keys):
        raise TargetDialogueMigrationError(
            f"source dialogue count mismatch: snapshot={declared_count}, canonical_keys={len(keys)}"
        )
    return keys


def inspect_project(project_id: str) -> dict[str, Any]:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    fingerprint = str(snapshot.get("source_fingerprint") or "").strip()
    if not fingerprint:
        raise TargetDialogueMigrationError("current SourceDramaSnapshot has no source_fingerprint")
    source_keys = _canonical_source_keys(snapshot)

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        all_rows = list(session.scalars(
            select(TargetDialogue).where(TargetDialogue.project_id == project_id)
        ).all())
        current_rows = [] if not source_keys else list(session.scalars(
            select(TargetDialogue).where(
                TargetDialogue.project_id == project_id,
                TargetDialogue.source_fingerprint == fingerprint,
                TargetDialogue.source_dialogue_key.in_(set(source_keys)),
            )
        ).all())

    current_ids = {row.id for row in current_rows}
    history_rows = [row for row in all_rows if row.id not in current_ids]
    return {
        "project_id": project_id,
        "source_fingerprint": fingerprint,
        "source_dialogue_count": len(source_keys),
        "persisted_target_dialogue_count": len(all_rows),
        "current_target_dialogue_count": len(current_rows),
        "historical_target_dialogue_count": len(history_rows),
        "current_source_keys": source_keys,
        "historical_row_ids": [row.id for row in history_rows],
    }


def backup_database(database_path: Path = DB_PATH) -> Path:
    source_path = Path(database_path).expanduser().resolve(strict=True)
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{source_path.stem}_before_target_dialogue_current_{timestamp}{source_path.suffix}"
    with sqlite3.connect(source_path) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)
    return backup_path


def migrate_project(project_id: str, *, database_path: Path = DB_PATH) -> dict[str, Any]:
    before = inspect_project(project_id)
    backup_path = backup_database(database_path)

    # Reuse the production service.  This creates/updates canonical current rows and intentionally
    # leaves old projection-level rows untouched as history.  Audio is not regenerated here.
    generated = generate_target_dialogue_text_v1(project_id)
    current = get_target_dialogue_v1(project_id)
    after = inspect_project(project_id)

    expected = int(after["source_dialogue_count"])
    if int(generated.get("dialogue_count") or 0) != expected:
        raise TargetDialogueMigrationError(
            f"generated current TargetDialogue count mismatch: expected={expected}, "
            f"actual={generated.get('dialogue_count')}"
        )
    if int(current.get("dialogue_count") or 0) != expected:
        raise TargetDialogueMigrationError(
            f"validated current TargetDialogue count mismatch: expected={expected}, "
            f"actual={current.get('dialogue_count')}"
        )
    if int(after["current_target_dialogue_count"]) != expected:
        raise TargetDialogueMigrationError(
            f"database current TargetDialogue count mismatch: expected={expected}, "
            f"actual={after['current_target_dialogue_count']}"
        )

    return {
        "status": "MIGRATED",
        "backup_path": str(backup_path),
        "before": before,
        "after": after,
        "bundle_status": current.get("status"),
        "review_count": int(current.get("review_count") or 0),
        "audio_ready_count": int(current.get("audio_ready_count") or 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, help="真实 V2 项目 ID")
    parser.add_argument(
        "--database",
        type=Path,
        default=DB_PATH,
        help="studio_v2.sqlite3 路径；默认使用当前 AI_DRAMA_STUDIO_HOME",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际执行迁移；不传时只做只读检查",
    )
    args = parser.parse_args()

    try:
        result = migrate_project(args.project_id, database_path=args.database) if args.apply else inspect_project(args.project_id)
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
