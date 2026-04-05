"""Tests for cron health check (Layer 1 + Layer 2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from core.schemas import CronTask
from core.supervisor.scheduler_manager import (
    SchedulerManager,
    _estimate_cron_interval_hours,
)


@pytest.fixture
def scheduler_mgr(tmp_path: Path) -> SchedulerManager:
    """Create a SchedulerManager with a temp anima dir."""
    anima = MagicMock()
    anima.memory.read_heartbeat_config.return_value = ""
    anima.memory.read_cron_config.return_value = ""
    mgr = SchedulerManager(
        anima=anima,
        anima_name="test_anima",
        anima_dir=tmp_path,
        emit_event=MagicMock(),
    )
    return mgr


def _notif_dir(tmp_path: Path) -> Path:
    return tmp_path / "state" / "background_notifications"


def _notif_files(tmp_path: Path) -> list[Path]:
    d = _notif_dir(tmp_path)
    if not d.exists():
        return []
    return sorted(d.glob("cron_health_*.md"))


def _make_task(name: str, schedule: str = "") -> CronTask:
    return CronTask(name=name, schedule=schedule, type="llm", description="")


# ── Layer 1: _check_cron_parse_health ─────────────────────────


class TestCheckCronParseHealth:
    """Layer 1 — immediate detection at setup/reload time."""

    def test_no_notification_when_all_registered_no_issues(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        tasks = [_make_task("t1", "0 9 * * *")]
        scheduler_mgr._check_cron_parse_health("schedule: 0 9 * * *", tasks, registered=1)
        assert _notif_files(tmp_path) == []

    def test_all_schedules_invalid(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        tasks = [_make_task("t1", "bad"), _make_task("t2", "also bad")]
        scheduler_mgr._check_cron_parse_health(
            "## t1\nschedule: bad\n## t2\nschedule: also bad", tasks, registered=0
        )
        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "2" in content  # task_count=2

    def test_indented_schedule_detected(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        raw = "```yaml\n  schedule: 0 9 * * *\n```"
        tasks = [_make_task("t1")]
        scheduler_mgr._check_cron_parse_health(raw, tasks, registered=0)
        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "schedule:" in content

    def test_indented_schedule_detected_even_with_valid_jobs(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """Indented schedule: lines are warned even when some jobs register."""
        raw = "## Good\nschedule: 0 9 * * *\n## Bad\n  schedule: 0 10 * * *"
        tasks = [_make_task("good", "0 9 * * *"), _make_task("bad")]
        scheduler_mgr._check_cron_parse_health(raw, tasks, registered=1)
        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "schedule:" in content

    def test_multiple_issues_combined_in_single_file(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """All-invalid + indented should produce exactly one file."""
        raw = "## t1\n  schedule: bad"
        tasks = [_make_task("t1", "bad")]
        scheduler_mgr._check_cron_parse_health(raw, tasks, registered=0)
        files = _notif_files(tmp_path)
        assert len(files) == 1

    def test_unrecognized_schedule_no_tasks(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        raw = 'schedule: "0 9 * * *"'
        scheduler_mgr._check_cron_parse_health(raw, tasks=[], registered=0)
        files = _notif_files(tmp_path)
        assert len(files) == 1

    def test_empty_config_no_notification(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        scheduler_mgr._check_cron_parse_health("", tasks=[], registered=0)
        assert _notif_files(tmp_path) == []


# ── Layer 1 integration: _setup_cron_tasks ────────────────────


class TestSetupCronTasksHealthIntegration:
    """_setup_cron_tasks invokes _check_cron_parse_health."""

    def test_invalid_cron_triggers_notification(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        scheduler_mgr._anima.memory.read_cron_config.return_value = (
            "## My Task\nschedule: INVALID\ntype: llm\nDo something\n"
        )
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        scheduler_mgr.scheduler = mock_scheduler

        scheduler_mgr._setup_cron_tasks()

        files = _notif_files(tmp_path)
        assert len(files) >= 1
        content = files[0].read_text(encoding="utf-8")
        assert "1" in content  # 1 task defined

    def test_valid_cron_no_notification(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        scheduler_mgr._anima.memory.read_cron_config.return_value = (
            "## My Task\nschedule: 0 9 * * *\ntype: llm\nDo something\n"
        )
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        scheduler_mgr.scheduler = mock_scheduler

        scheduler_mgr._setup_cron_tasks()

        assert _notif_files(tmp_path) == []


# ── Layer 2: _cron_health_tick ────────────────────────────────


class TestCronHealthTick:
    """Layer 2 — periodic health check every 3 hours."""

    @pytest.mark.asyncio
    async def test_no_execution_triggers_notification(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        mock_scheduler = MagicMock()
        job_cron = MagicMock()
        job_cron.id = "test_anima_cron_0"
        job_health = MagicMock()
        job_health.id = "test_anima_cron_health"
        mock_scheduler.get_jobs.return_value = [job_cron, job_health]
        scheduler_mgr.scheduler = mock_scheduler

        scheduler_mgr._anima._activity._load_entries = MagicMock(return_value=[])

        await scheduler_mgr._cron_health_tick()

        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "1" in content  # 1 cron job (health job excluded)

    @pytest.mark.asyncio
    async def test_with_executions_no_notification(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        mock_scheduler = MagicMock()
        job = MagicMock()
        job.id = "test_anima_cron_0"
        mock_scheduler.get_jobs.return_value = [job]
        scheduler_mgr.scheduler = mock_scheduler

        entry = MagicMock()
        scheduler_mgr._anima._activity._load_entries = MagicMock(return_value=[entry])

        await scheduler_mgr._cron_health_tick()

        assert _notif_files(tmp_path) == []

    @pytest.mark.asyncio
    async def test_no_cron_jobs_no_notification(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        scheduler_mgr.scheduler = mock_scheduler

        await scheduler_mgr._cron_health_tick()

        assert _notif_files(tmp_path) == []

    @pytest.mark.asyncio
    async def test_health_job_excluded_from_count(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        mock_scheduler = MagicMock()
        job_health = MagicMock()
        job_health.id = "test_anima_cron_health"
        mock_scheduler.get_jobs.return_value = [job_health]
        scheduler_mgr.scheduler = mock_scheduler

        await scheduler_mgr._cron_health_tick()

        assert _notif_files(tmp_path) == []

    @pytest.mark.asyncio
    async def test_activity_error_handled_gracefully(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        mock_scheduler = MagicMock()
        job = MagicMock()
        job.id = "test_anima_cron_0"
        mock_scheduler.get_jobs.return_value = [job]
        scheduler_mgr.scheduler = mock_scheduler

        scheduler_mgr._anima._activity._load_entries = MagicMock(
            side_effect=RuntimeError("disk error")
        )

        await scheduler_mgr._cron_health_tick()

        assert _notif_files(tmp_path) == []


# ── _setup_cron_health_check ──────────────────────────────────


class TestSetupCronHealthCheck:
    def test_registers_job(self, scheduler_mgr: SchedulerManager) -> None:
        mock_scheduler = MagicMock()
        scheduler_mgr.scheduler = mock_scheduler

        scheduler_mgr._setup_cron_health_check()

        mock_scheduler.add_job.assert_called_once()
        call_kwargs = mock_scheduler.add_job.call_args
        assert call_kwargs[1]["id"] == "test_anima_cron_health"

    def test_no_scheduler_no_error(self, scheduler_mgr: SchedulerManager) -> None:
        scheduler_mgr.scheduler = None
        scheduler_mgr._setup_cron_health_check()

    def test_no_anima_no_error(self, scheduler_mgr: SchedulerManager) -> None:
        scheduler_mgr._anima = None  # type: ignore[assignment]
        mock_scheduler = MagicMock()
        scheduler_mgr.scheduler = mock_scheduler
        scheduler_mgr._setup_cron_health_check()
        mock_scheduler.add_job.assert_not_called()


# ── _write_cron_health_notification ───────────────────────────


class TestWriteCronHealthNotification:
    def test_creates_md_file(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        scheduler_mgr._write_cron_health_notification("Test warning message")

        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "Test warning message" in content
        assert "⚠️" in content

    def test_write_failure_does_not_raise(
        self, scheduler_mgr: SchedulerManager
    ) -> None:
        scheduler_mgr._anima_dir = Path("/nonexistent/path/should/fail")
        scheduler_mgr._write_cron_health_notification("msg")


# ── _estimate_cron_interval_hours ─────────────────────────────


class TestEstimateCronIntervalHours:
    """Unit tests for the schedule-interval estimation helper."""

    def test_weekly_job_returns_8_days(self) -> None:
        # dow = specific integer, dom = *
        assert _estimate_cron_interval_hours("0 17 * * 4") == 8 * 24.0

    def test_weekly_job_sunday(self) -> None:
        assert _estimate_cron_interval_hours("30 9 * * 0") == 8 * 24.0

    def test_monthly_job_returns_32_days(self) -> None:
        # dom = specific integer, dow = *
        assert _estimate_cron_interval_hours("0 9 1 * *") == 32 * 24.0

    def test_monthly_job_15th(self) -> None:
        assert _estimate_cron_interval_hours("0 0 15 * *") == 32 * 24.0

    def test_daily_job_returns_25h(self) -> None:
        # specific hour, dom/dow = *
        assert _estimate_cron_interval_hours("0 9 * * *") == 25.0

    def test_daily_job_multiple_hours(self) -> None:
        # comma-separated hours are "not *" and not step → treated as daily
        assert _estimate_cron_interval_hours("0 9,17 * * *") == 25.0

    def test_hourly_step_returns_default(self) -> None:
        # "*/2" starts with "*/" → sub-daily
        from core.supervisor.scheduler_manager import _HEALTH_CHECK_HOURS
        assert _estimate_cron_interval_hours("0 */2 * * *") == float(_HEALTH_CHECK_HOURS)

    def test_every_minute_returns_default(self) -> None:
        from core.supervisor.scheduler_manager import _HEALTH_CHECK_HOURS
        assert _estimate_cron_interval_hours("* * * * *") == float(_HEALTH_CHECK_HOURS)

    def test_invalid_expression_returns_default(self) -> None:
        from core.supervisor.scheduler_manager import _HEALTH_CHECK_HOURS
        assert _estimate_cron_interval_hours("bad schedule") == float(_HEALTH_CHECK_HOURS)
        assert _estimate_cron_interval_hours("") == float(_HEALTH_CHECK_HOURS)


# ── Layer 2 (interval-aware): _cron_health_tick ───────────────


class TestCronHealthTickIntervalThreshold:
    """Verify that weekly/monthly jobs use appropriate lookback windows."""

    def _make_job(self, job_id: str, task: CronTask) -> MagicMock:
        job = MagicMock()
        job.id = job_id
        job.args = [task]
        return job

    @pytest.mark.asyncio
    async def test_weekly_job_no_false_positive_within_8_days(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """Weekly job executed 4 days ago should NOT trigger an alert."""
        task = CronTask(name="weekly", schedule="0 17 * * 4", type="llm", description="")
        job = self._make_job("test_anima_cron_0", task)
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job]
        scheduler_mgr.scheduler = mock_scheduler

        # 3-hour window → empty (old logic would alert here)
        # 8-day window  → has an entry (correct: was executed recently enough)
        def load_entries(hours: float, types: list[str]) -> list:
            return [MagicMock()] if hours >= 8 * 24 else []

        scheduler_mgr._anima._activity._load_entries = MagicMock(side_effect=load_entries)

        await scheduler_mgr._cron_health_tick()

        assert _notif_files(tmp_path) == [], "Weekly job should not trigger false positive"

    @pytest.mark.asyncio
    async def test_weekly_job_triggers_alert_if_missed_full_week(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """Weekly job not executed in 8+ days SHOULD trigger an alert."""
        task = CronTask(name="weekly", schedule="0 17 * * 4", type="llm", description="")
        job = self._make_job("test_anima_cron_0", task)
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job]
        scheduler_mgr.scheduler = mock_scheduler

        # No executions even in the 8-day window
        scheduler_mgr._anima._activity._load_entries = MagicMock(return_value=[])

        await scheduler_mgr._cron_health_tick()

        files = _notif_files(tmp_path)
        assert len(files) == 1, "Weekly job missed for 8+ days should alert"

    @pytest.mark.asyncio
    async def test_monthly_job_no_false_positive_within_32_days(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """Monthly job executed 20 days ago should NOT trigger an alert."""
        task = CronTask(name="monthly", schedule="0 9 1 * *", type="llm", description="")
        job = self._make_job("test_anima_cron_0", task)
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job]
        scheduler_mgr.scheduler = mock_scheduler

        def load_entries(hours: float, types: list[str]) -> list:
            return [MagicMock()] if hours >= 32 * 24 else []

        scheduler_mgr._anima._activity._load_entries = MagicMock(side_effect=load_entries)

        await scheduler_mgr._cron_health_tick()

        assert _notif_files(tmp_path) == [], "Monthly job should not trigger false positive"

    @pytest.mark.asyncio
    async def test_mixed_jobs_uses_minimum_threshold(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """With daily + weekly jobs, the daily (minimum) threshold should be used."""
        task_daily = CronTask(name="daily", schedule="0 9 * * *", type="llm", description="")
        task_weekly = CronTask(name="weekly", schedule="0 17 * * 4", type="llm", description="")
        job1 = self._make_job("test_anima_cron_0", task_daily)
        job2 = self._make_job("test_anima_cron_1", task_weekly)
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job1, job2]
        scheduler_mgr.scheduler = mock_scheduler

        calls_hours: list[float] = []

        def load_entries(hours: float, types: list[str]) -> list:
            calls_hours.append(hours)
            return []

        scheduler_mgr._anima._activity._load_entries = MagicMock(side_effect=load_entries)

        await scheduler_mgr._cron_health_tick()

        assert len(calls_hours) == 1
        assert calls_hours[0] == 25.0, f"Expected daily threshold 25.0, got {calls_hours[0]}"

    @pytest.mark.asyncio
    async def test_daily_job_uses_25h_threshold(
        self, scheduler_mgr: SchedulerManager, tmp_path: Path
    ) -> None:
        """Daily job uses 25-hour lookback window."""
        task = CronTask(name="daily", schedule="0 9 * * *", type="llm", description="")
        job = self._make_job("test_anima_cron_0", task)
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = [job]
        scheduler_mgr.scheduler = mock_scheduler

        calls_hours: list[float] = []

        def load_entries(hours: float, types: list[str]) -> list:
            calls_hours.append(hours)
            return [MagicMock()]  # has execution

        scheduler_mgr._anima._activity._load_entries = MagicMock(side_effect=load_entries)

        await scheduler_mgr._cron_health_tick()

        assert calls_hours[0] == 25.0
        assert _notif_files(tmp_path) == []


# ── reload_schedule includes health check ─────────────────────


class TestReloadScheduleIncludesHealthCheck:
    def test_reload_calls_health_check_setup(
        self, scheduler_mgr: SchedulerManager
    ) -> None:
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        scheduler_mgr.scheduler = mock_scheduler

        with patch.object(
            scheduler_mgr, "_setup_cron_health_check"
        ) as mock_health:
            scheduler_mgr.reload_schedule("test_anima")

        mock_health.assert_called_once()
