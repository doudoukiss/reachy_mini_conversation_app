from __future__ import annotations

import json
from pathlib import Path

from embodied_stack.action_plane.bundles import ActionBundleStore
from embodied_stack.config import get_settings
from embodied_stack.demo.episodes.service import EpisodeStore


def run_inspection() -> int:
    settings = get_settings()
    episode_store = EpisodeStore(settings.episode_export_dir)
    bundle_store = ActionBundleStore(settings.blink_action_plane_export_dir)

    episodes = episode_store.list().items
    if not episodes:
        print("latest_episode=none")
        print("error=no_episode_exports_found")
        return 1

    latest_episode = episodes[0]
    action_index_path = latest_episode.derived_artifact_files.get("action_bundle_index")
    if not action_index_path:
        print(f"latest_episode={latest_episode.episode_id}")
        print("error=episode_missing_action_bundle_index")
        return 1

    action_index_file = Path(action_index_path)
    if not action_index_file.exists():
        print(f"latest_episode={latest_episode.episode_id}")
        print(f"error=missing_action_bundle_index:{action_index_file}")
        return 1

    index_payload = json.loads(action_index_file.read_text(encoding="utf-8"))
    bundle_refs = index_payload.get("bundles") or []
    print(
        "latest_episode "
        f"id={latest_episode.episode_id} "
        f"action_bundle_index={action_index_file} "
        f"linked_bundles={len(bundle_refs)}"
    )

    latest_bundle = bundle_store.list_bundles(limit=1).items
    latest_replay = bundle_store.list_replays(limit=1)
    if not latest_bundle and not latest_replay:
        print("error=no_action_bundles_or_replays_found")
        return 1

    if latest_bundle:
        bundle = latest_bundle[0]
        bundle_detail = bundle_store.get_bundle_detail(bundle.bundle_id)
        manifest_path = bundle_store.bundles_dir / bundle.bundle_id / bundle_store.MANIFEST_FILE
        if bundle_detail is None or not manifest_path.exists():
            print(f"error=invalid_bundle_manifest:{bundle.bundle_id}")
            return 1
        print(
            "latest_bundle "
            f"id={bundle.bundle_id} "
            f"status={(bundle.final_status.value if hasattr(bundle.final_status, 'value') else bundle.final_status) or '-'} "
            f"manifest={manifest_path}"
        )

    if latest_replay:
        replay = latest_replay[0]
        replay_manifest = replay.artifact_files.get("manifest")
        if not replay_manifest or not Path(replay_manifest).exists():
            print(f"error=invalid_replay_manifest:{replay.replay_id}")
            return 1
        print(
            "latest_replay "
            f"id={replay.replay_id} "
            f"status={replay.status.value} "
            f"manifest={replay_manifest}"
        )

    print("inspection=ok")
    return 0


def main() -> None:
    raise SystemExit(run_inspection())


__all__ = ["main", "run_inspection"]
