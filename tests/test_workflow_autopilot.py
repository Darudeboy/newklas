import unittest
from unittest.mock import MagicMock, patch

from core.orchestrator import run_workflow_autopilot


def _base_result(**kw):
    r = {
        "success": True,
        "release_key": "HRPRELEASE-1",
        "project_key": "HRP",
        "profile_name": "auto",
        "current_stage": "S1",
        "next_allowed_transition": "S2",
        "ready_for_transition": True,
        "terminal_stage": False,
        "auto_failed": [],
        "manual_pending": [],
    }
    r.update(kw)
    return r


class WorkflowAutopilotTest(unittest.TestCase):
    def test_dry_run_blocked(self):
        j = MagicMock()
        out = run_workflow_autopilot(j, "HRPRELEASE-1", dry_run=True)
        self.assertFalse(out["ok"])
        self.assertEqual(out["stop_reason"], "dry_run_blocked")
        j.transition_issue_to_status.assert_not_called()

    @patch("core.orchestrator.run_release_check")
    def test_check_failed_on_first_check(self, mock_check):
        mock_check.return_value = {"success": False, "message": "нет задачи"}
        j = MagicMock()
        out = run_workflow_autopilot(j, "HRPRELEASE-1", dry_run=False)
        self.assertEqual(out["stop_reason"], "check_failed")
        self.assertFalse(out["ok"])

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_terminal_immediately(self, _sleep, mock_check):
        mock_check.return_value = _base_result(
            terminal_stage=True,
            ready_for_transition=False,
            next_allowed_transition=None,
            terminal_reason="Уже утверждён",
        )
        j = MagicMock()
        out = run_workflow_autopilot(j, "HRPRELEASE-1", dry_run=False)
        self.assertTrue(out["ok"])
        self.assertEqual(out["stop_reason"], "terminal")
        j.transition_issue_to_status.assert_not_called()

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_blocked_not_ready(self, _sleep, mock_check):
        mock_check.return_value = _base_result(
            ready_for_transition=False,
        )
        j = MagicMock()
        out = run_workflow_autopilot(j, "HRPRELEASE-1", dry_run=False)
        self.assertFalse(out["ok"])
        self.assertEqual(out["stop_reason"], "blocked")
        j.transition_issue_to_status.assert_not_called()

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_jira_error_on_transition(self, _sleep, mock_check):
        mock_check.return_value = _base_result()
        j = MagicMock()
        j.transition_issue_to_status.return_value = (False, "permission denied")
        out = run_workflow_autopilot(j, "HRPRELEASE-1", dry_run=False)
        self.assertFalse(out["ok"])
        self.assertEqual(out["stop_reason"], "jira_error")
        self.assertEqual(out["message"], "permission denied")

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_max_steps_after_one_transition(self, _sleep, mock_check):
        j = MagicMock()
        j.transition_issue_to_status.return_value = (True, "ok")
        mock_check.side_effect = [
            _base_result(current_stage="S1", next_allowed_transition="S2"),
            _base_result(
                current_stage="S2",
                next_allowed_transition="S3",
                ready_for_transition=True,
            ),
        ]
        out = run_workflow_autopilot(
            j,
            "HRPRELEASE-1",
            dry_run=False,
            max_steps=1,
            post_transition_delay_sec=0.01,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["stop_reason"], "max_steps")
        self.assertEqual(len(out["steps"]), 1)

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_stuck_when_status_unchanged(self, _sleep, mock_check):
        j = MagicMock()
        j.transition_issue_to_status.return_value = (True, "ok")
        same = _base_result(
            current_stage="S1",
            next_allowed_transition="S2",
            ready_for_transition=True,
        )
        mock_check.side_effect = [
            _base_result(
                current_stage="S1",
                next_allowed_transition="S2",
                ready_for_transition=True,
            ),
            same,
            same,
            same,
        ]
        out = run_workflow_autopilot(
            j,
            "HRPRELEASE-1",
            dry_run=False,
            max_steps=10,
            post_transition_delay_sec=0.01,
            stuck_threshold=3,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["stop_reason"], "stuck")
        self.assertEqual(len(out["steps"]), 1)

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_one_transition_then_terminal(self, _sleep, mock_check):
        j = MagicMock()
        j.transition_issue_to_status.return_value = (True, "ok")
        mock_check.side_effect = [
            _base_result(
                current_stage="S1",
                next_allowed_transition="S2",
            ),
            _base_result(
                current_stage="S2",
                terminal_stage=True,
                ready_for_transition=False,
                next_allowed_transition=None,
                terminal_reason="Финал",
            ),
        ]
        out = run_workflow_autopilot(
            j,
            "HRPRELEASE-1",
            dry_run=False,
            post_transition_delay_sec=0.01,
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["stop_reason"], "terminal")
        self.assertEqual(len(out["steps"]), 1)

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_register_distribution_before_ppsi_and_fail(self, _sleep, mock_check):
        j = MagicMock()
        j.register_distribution.return_value = (False, "ke required")
        j.transition_issue_to_status.return_value = (True, "ok")
        mock_check.return_value = _base_result(
            current_stage="ПСИ",
            next_allowed_transition="Согласование ППСИ",
            ready_for_transition=True,
        )
        out = run_workflow_autopilot(
            j,
            "HRPRELEASE-1",
            dry_run=False,
            max_steps=10,
            post_transition_delay_sec=0.01,
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["stop_reason"], "jira_error")
        self.assertIn("ke required", out["message"])
        # must stop before transition
        j.transition_issue_to_status.assert_not_called()
        self.assertEqual(len(out["steps"]), 1)
        self.assertEqual(out["steps"][0]["to_status"], "register_distribution")

    @patch("core.orchestrator.run_release_check")
    @patch("core.orchestrator.time.sleep", return_value=None)
    def test_register_distribution_before_ppsi_and_ok(self, _sleep, mock_check):
        j = MagicMock()
        j.register_distribution.return_value = (True, "registered")
        j.transition_issue_to_status.return_value = (True, "ok")
        mock_check.side_effect = [
            _base_result(
                current_stage="ПСИ",
                next_allowed_transition="Согласование ППСИ",
                ready_for_transition=True,
            ),
            _base_result(
                current_stage="Согласование ППСИ",
                terminal_stage=True,
                ready_for_transition=False,
                next_allowed_transition=None,
                terminal_reason="Финал",
            ),
        ]
        out = run_workflow_autopilot(
            j,
            "HRPRELEASE-1",
            dry_run=False,
            max_steps=10,
            post_transition_delay_sec=0.01,
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["stop_reason"], "terminal")
        self.assertEqual(len(out["steps"]), 2)
        self.assertEqual(out["steps"][0]["to_status"], "register_distribution")
        self.assertEqual(out["steps"][1]["to_status"], "Согласование ППСИ")


if __name__ == "__main__":
    unittest.main()
