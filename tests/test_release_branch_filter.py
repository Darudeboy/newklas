import unittest

from release_pr_status import (
    _extract_prs_from_dev_status,
    _is_master_like_branch,
    _is_release_target_branch,
    _normalize_branch_name,
)
from story_checker import format_story_check_report


class ReleaseBranchFilterTest(unittest.TestCase):
    def test_normalize_refs_heads(self):
        self.assertEqual(
            _normalize_branch_name("refs/heads/release/HRPRELEASE-1"),
            "release/hrprelease-1",
        )

    def test_master_like(self):
        self.assertTrue(_is_master_like_branch("master"))
        self.assertTrue(_is_master_like_branch("main"))
        self.assertTrue(_is_master_like_branch("refs/heads/master"))
        self.assertTrue(_is_master_like_branch("origin/main"))
        self.assertFalse(_is_master_like_branch("release/HRPRELEASE-1"))

    def test_release_target(self):
        rk = "HRPRELEASE-76202"
        self.assertTrue(_is_release_target_branch(f"release/{rk}", rk))
        self.assertTrue(
            _is_release_target_branch(f"refs/heads/release/{rk}", rk)
        )
        self.assertTrue(
            _is_release_target_branch(f"origin/release/{rk}", rk)
        )
        self.assertFalse(_is_release_target_branch("master", rk))
        self.assertFalse(
            _is_release_target_branch("release/HRPRELEASE-OTHER", rk)
        )

    def test_dev_status_filter_release(self):
        rk = "HRPRELEASE-10"
        raw = [
            {
                "url": "http://bb/pr/1",
                "name": "to release",
                "status": "MERGED",
                "destination": {"branch": f"release/{rk}"},
            },
            {
                "url": "http://bb/pr/2",
                "name": "to master",
                "status": "MERGED",
                "destination": {"branch": "master"},
            },
        ]
        filtered = _extract_prs_from_dev_status(
            raw,
            branch_predicate=lambda b: _is_release_target_branch(b, rk),
        )
        self.assertEqual(len(filtered), 1)
        self.assertIn("release/", filtered[0]["target_branch"].lower())


class StoryReportFormatTest(unittest.TestCase):
    def test_format_empty_stories(self):
        text = format_story_check_report(
            {
                "success": True,
                "release_key": "HRPRELEASE-1",
                "release_summary": "test",
                "stories_total": 0,
                "stories_ok": 0,
                "stories_failed": 0,
                "warnings_total": 0,
                "stories": [],
            }
        )
        self.assertIn("HRPRELEASE-1", text)
        self.assertIn("не найдено Story", text)

    def test_format_error(self):
        text = format_story_check_report(
            {"success": False, "message": "нет ключа"}
        )
        self.assertIn("нет ключа", text)


if __name__ == "__main__":
    unittest.main()
