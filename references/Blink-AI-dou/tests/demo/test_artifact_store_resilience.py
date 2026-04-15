from __future__ import annotations

from embodied_stack.demo.episodes import EpisodeStore
from embodied_stack.demo.report_store import DemoReportStore
from embodied_stack.demo.shift_reports import ShiftReportStore


def test_demo_report_store_skips_invalid_summaries(tmp_path):
    store = DemoReportStore(tmp_path / "demo_runs")
    broken_dir = store.report_dir / "broken-run"
    broken_dir.mkdir(parents=True)
    (broken_dir / "summary.json").write_text("{broken", encoding="utf-8")

    assert store.list().items == []
    assert store.get("broken-run") is None


def test_shift_report_store_skips_invalid_summaries(tmp_path):
    store = ShiftReportStore(tmp_path / "shift_reports")
    broken_dir = store.report_dir / "broken-report"
    broken_dir.mkdir(parents=True)
    (broken_dir / "summary.json").write_text("{broken", encoding="utf-8")
    (broken_dir / "report.json").write_text("{broken", encoding="utf-8")

    assert store.list().items == []
    assert store.get("broken-report") is None


def test_episode_store_skips_invalid_summaries(tmp_path):
    store = EpisodeStore(tmp_path / "episodes")
    broken_dir = store.export_dir / "broken-episode"
    broken_dir.mkdir(parents=True)
    (broken_dir / "summary.json").write_text("{broken", encoding="utf-8")
    (broken_dir / "episode.json").write_text("{broken", encoding="utf-8")

    assert store.list().items == []
    assert store.get("broken-episode") is None
