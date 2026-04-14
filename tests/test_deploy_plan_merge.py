import unittest


from master_analyzer import merge_deploy_plan_into_template_storage, build_component_table_rows


class DeployPlanMergeTest(unittest.TestCase):
    def test_build_component_table_rows_puts_service_into_component_column(self):
        rows = build_component_table_rows(["app-smart-profile"], team_label="Команда")
        self.assertIn("<td>app-smart-profile</td>", rows)

    def test_merge_replaces_header_and_services_and_preserves_other_html(self):
        template_storage = """
        <div>
          <h1>Deploy plan: OLD-REL</h1>
          <p><strong>Релиз:</strong> OLD-REL<br/>
          <strong>Название:</strong> old summary<br/>
          <strong>Команда:</strong> old team</p>
          <h2>План установки</h2>
          <table>
            <tbody>
              <tr>
                <th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>
              </tr>
              <tr><td>1</td><td>Команда</td><td>old-component</td><td>old</td><td></td><td></td></tr>
            </tbody>
          </table>
          <ac:structured-macro ac:name="labels"><ac:parameter ac:name="x">KEEP</ac:parameter></ac:structured-macro>
        </div>
        """

        release_header_html = """
<h1>Deploy plan: NEW-REL</h1>
<p><strong>Релиз:</strong> NEW-REL<br/>
<strong>Название:</strong> new summary<br/>
<strong>Команда:</strong> new team</p>
""".strip()

        services_rows_html = build_component_table_rows(["app-smart-profile"], team_label="Команда")

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_header_html=release_header_html,
            services_rows_html=services_rows_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None

        self.assertIn("Deploy plan: NEW-REL", merged)
        self.assertIn("app-smart-profile", merged)
        self.assertNotIn("old-component", merged)
        self.assertIn("KEEP", merged)

    def test_merge_inserts_services_if_services_block_missing(self):
        template_storage = """
        <div>
          <h1>Deploy plan: OLD-REL</h1>
          <p><strong>Релиз:</strong> OLD-REL<br/>
          <strong>Название:</strong> old summary<br/>
          <strong>Команда:</strong> old team</p>
          <!-- component table missing -->
          <ac:structured-macro ac:name="some-macro"><ac:parameter ac:name="x">KEEP2</ac:parameter></ac:structured-macro>
        </div>
        """

        release_header_html = """
<h1>Deploy plan: NEW-REL</h1>
<p><strong>Релиз:</strong> NEW-REL<br/>
<strong>Название:</strong> new summary<br/>
<strong>Команда:</strong> new team</p>
""".strip()

        services_rows_html = build_component_table_rows(["app-smart-profile"], team_label="Команда")

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_header_html=release_header_html,
            services_rows_html=services_rows_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertIn("Deploy plan: NEW-REL", merged)
        self.assertIn("app-smart-profile", merged)
        self.assertIn("KEEP2", merged)

    def test_merge_tolerates_template_variations_and_macros(self):
        template_storage = """
        <div>
          <h1><span>Deploy</span> plan: OLD-REL</h1>
          <ac:structured-macro ac:name="info"><ac:parameter ac:name="title">KEEP_INFO</ac:parameter></ac:structured-macro>
          <p>какой-то текст</p>
          <h2>План установки</h2>
          <table>
            <tbody>
              <tr>
                <th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>
              </tr>
              <tr><td>1</td><td>Команда</td><td>old-component</td><td>old</td><td></td><td></td></tr>
            </tbody>
          </table>
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

        services_rows_html = build_component_table_rows(["app-smart-profile"], team_label="Команда")

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_header_html=release_header_html,
            services_rows_html=services_rows_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertIn("Deploy plan: NEW-REL", merged)
        self.assertIn("app-smart-profile", merged)
        self.assertIn("KEEP_AFTER", merged)


if __name__ == "__main__":
    unittest.main()

