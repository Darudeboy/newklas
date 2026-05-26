import unittest
from unittest.mock import MagicMock

from core.orchestrator import (
    SUCCESS_COMMENT_TEXT,
    maybe_post_success_comment,
)


def _ready_result(**overrides):
    base = {
        "success": True,
        "release_key": "HRPRELEASE-1",
        "auto_failed": [],
        "ready_for_transition": True,
        "next_allowed_transition": "Согласование ППСИ",
    }
    base.update(overrides)
    return base


class TestMaybePostSuccessComment(unittest.TestCase):
    def test_posts_when_ready(self):
        jira = MagicMock()
        jira.has_recent_comment.return_value = False
        jira.add_issue_comment.return_value = (True, "ok")

        ok, msg = maybe_post_success_comment(jira, _ready_result())

        self.assertTrue(ok)
        jira.add_issue_comment.assert_called_once_with(
            "HRPRELEASE-1", SUCCESS_COMMENT_TEXT
        )

    def test_skips_when_not_ready(self):
        jira = MagicMock()
        ok, msg = maybe_post_success_comment(
            jira, _ready_result(ready_for_transition=False)
        )
        self.assertFalse(ok)
        self.assertEqual(msg, "not ready for transition")
        jira.add_issue_comment.assert_not_called()

    def test_skips_when_already_posted(self):
        jira = MagicMock()
        jira.has_recent_comment.return_value = True

        ok, msg = maybe_post_success_comment(jira, _ready_result())

        self.assertFalse(ok)
        self.assertEqual(msg, "already posted")
        jira.add_issue_comment.assert_not_called()

    def test_skips_dry_run(self):
        jira = MagicMock()
        ok, msg = maybe_post_success_comment(
            jira, _ready_result(), dry_run=True
        )
        self.assertFalse(ok)
        self.assertIn("dry-run", msg)


if __name__ == "__main__":
    unittest.main()
