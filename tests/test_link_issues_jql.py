import unittest

from core.jira_jql import build_fix_version_link_jql


class TestLinkIssuesJql(unittest.TestCase):
    def test_project_equals_not_in_list(self):
        jql = build_fix_version_link_jql("HRM", "2025.1")
        self.assertIn("project = HRM", jql)
        self.assertNotIn("project IN", jql)
        self.assertIn('fixVersion = "2025.1"', jql)
        self.assertIn("issuetype IN (Bug, Story)", jql)

    def test_escapes_quotes_in_fix_version(self):
        jql = build_fix_version_link_jql("HRC", '1.0"beta')
        self.assertIn('fixVersion = "1.0\\"beta"', jql)

    def test_requires_project_key(self):
        with self.assertRaises(ValueError):
            build_fix_version_link_jql("", "1.0")

    def test_requires_fix_version(self):
        with self.assertRaises(ValueError):
            build_fix_version_link_jql("HRM", "")


if __name__ == "__main__":
    unittest.main()
