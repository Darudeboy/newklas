import unittest


from master_analyzer import merge_deploy_plan_into_template_storage


class DeployPlanMergeTest(unittest.TestCase):
    def test_merge_replaces_header_and_services_and_preserves_other_html(self):
        template_storage = """
        <div>
          <h1>Deploy plan: OLD-REL</h1>
          <p><strong>Релиз:</strong> OLD-REL<br/>
          <strong>Название:</strong> old summary<br/>
          <strong>Команда:</strong> old team</p>
          <h2>Сервисы (влитые в master)</h2>
          <table><tr><td>OLD TABLE</td></tr></table>
          <p><em>Сгенерировано инструментом Blast.</em></p>
          <ac:structured-macro ac:name="labels"><ac:parameter ac:name="x">KEEP</ac:parameter></ac:structured-macro>
        </div>
        """

        release_header_html = """
<h1>Deploy plan: NEW-REL</h1>
<p><strong>Релиз:</strong> NEW-REL<br/>
<strong>Название:</strong> new summary<br/>
<strong>Команда:</strong> new team</p>
""".strip()

        services_section_html = """
<h2>Сервисы (влитые в master)</h2>
<table><tr><td>NEW TABLE</td></tr></table>
<p><em>Сгенерировано инструментом Blast.</em></p>
""".strip()

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_header_html=release_header_html,
            services_section_html=services_section_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None

        self.assertIn("Deploy plan: NEW-REL", merged)
        self.assertIn("NEW TABLE", merged)
        self.assertNotIn("OLD TABLE", merged)
        self.assertIn("KEEP", merged)

    def test_merge_inserts_services_if_services_block_missing(self):
        template_storage = """
        <div>
          <h1>Deploy plan: OLD-REL</h1>
          <p><strong>Релиз:</strong> OLD-REL<br/>
          <strong>Название:</strong> old summary<br/>
          <strong>Команда:</strong> old team</p>
          <!-- services block missing -->
          <ac:structured-macro ac:name="some-macro"><ac:parameter ac:name="x">KEEP2</ac:parameter></ac:structured-macro>
        </div>
        """

        release_header_html = """
<h1>Deploy plan: NEW-REL</h1>
<p><strong>Релиз:</strong> NEW-REL<br/>
<strong>Название:</strong> new summary<br/>
<strong>Команда:</strong> new team</p>
""".strip()

        services_section_html = """
<h2>Сервисы (влитые в master)</h2>
<table><tr><td>NEW TABLE</td></tr></table>
<p><em>Сгенерировано инструментом Blast.</em></p>
""".strip()

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_header_html=release_header_html,
            services_section_html=services_section_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertIn("Deploy plan: NEW-REL", merged)
        self.assertIn("NEW TABLE", merged)
        self.assertIn("KEEP2", merged)

    def test_merge_tolerates_template_variations_and_macros(self):
        template_storage = """
        <div>
          <h1><span>Deploy</span> plan: OLD-REL</h1>
          <ac:structured-macro ac:name="info"><ac:parameter ac:name="title">KEEP_INFO</ac:parameter></ac:structured-macro>
          <p>какой-то текст</p>
          <h2>Сервисы (влитые в master)</h2>
          <ac:structured-macro ac:name="some-table-macro"><ac:parameter ac:name="x">KEEP_TABLE_MACRO</ac:parameter></ac:structured-macro>
          <p>заметка может быть любая, не обязательно em</p>
          <h2>Другая секция</h2>
          <p>KEEP_AFTER</p>
        </div>
        """

        release_header_html = """
<h1>Deploy plan: NEW-REL</h1>
<p><strong>Релиз:</strong> NEW-REL<br/>
<strong>Название:</strong> new summary<br/>
<strong>Команда:</strong> new team</p>
""".strip()

        services_section_html = """
<h2>Сервисы (влитые в master)</h2>
<table><tr><td>NEW TABLE</td></tr></table>
<p><em>Сгенерировано инструментом Blast.</em></p>
""".strip()

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_header_html=release_header_html,
            services_section_html=services_section_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertIn("Deploy plan: NEW-REL", merged)
        self.assertIn("NEW TABLE", merged)
        self.assertIn("KEEP_AFTER", merged)


if __name__ == "__main__":
    unittest.main()

