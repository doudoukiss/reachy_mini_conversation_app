from __future__ import annotations

from pathlib import Path

from embodied_stack.persistence.json_files import _rotate_backups


def test_rotate_backups_ignores_raced_oldest_unlink(monkeypatch, tmp_path: Path):
    path = tmp_path / "state.json"
    oldest = tmp_path / "state.json.bak2"
    oldest.write_text("old", encoding="utf-8")

    original_unlink = Path.unlink

    def _raced_unlink(self: Path, *args, **kwargs):
        if self == oldest:
            raise FileNotFoundError(self)
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _raced_unlink)

    _rotate_backups(path, 2)
