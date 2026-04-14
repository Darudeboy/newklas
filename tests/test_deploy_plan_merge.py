import unittest


from master_analyzer import (
    build_component_table_rows,
    extract_release_date_iso,
    format_ru_date,
    merge_deploy_plan_into_template_storage,
)


class DeployPlanMergeTest(unittest.TestCase):
    def test_build_component_table_rows_puts_service_into_component_column(self):
        rows = build_component_table_rows(["app-smart-profile"], team_label="Команда")
        self.assertIn("<td>app-smart-profile</td>", rows)

    def test_extract_release_date_iso(self):
        self.assertEqual(
            extract_release_date_iso("HRPRELEASE-76202 - Релиз-2025-02-07"),
            "2025-02-07",
        )

    def test_format_ru_date(self):
        self.assertEqual(format_ru_date("2025-02-07"), "07 февр. 2025 г.")

    def test_merge_replaces_header_and_services_and_preserves_other_html(self):
        template_storage = """
        <div>
          <h1>Deploy plan: OLD-REL</h1>
          <h2>Релиз</h2>
          <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-REL</ac:parameter></ac:structured-macro>
          <h2>План установки</h2>
          <table>
            <tbody>
              <tr>
                <th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>
              </tr>
              <tr><td>1</td><td>Команда</td><td>old-component</td><td>old</td><td></td><td></td></tr>
            </tbody>
          </table>
          <h2>План отката</h2>
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

        install_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )
        rollback_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_key="NEW-REL",
            install_rows_html=install_rows_html,
            rollback_rows_html=rollback_rows_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None

        self.assertIn(">NEW-REL</ac:parameter>", merged)
        self.assertIn("app-smart-profile", merged)
        self.assertNotIn("old-component", merged)
        self.assertIn("KEEP", merged)

    def test_merge_inserts_services_if_services_block_missing(self):
        template_storage = """
        <div>
          <h2>Релиз</h2>
          <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-REL</ac:parameter></ac:structured-macro>
          <!-- tables missing -->
          <h2>Другая секция</h2>
          <ac:structured-macro ac:name="some-macro"><ac:parameter ac:name="x">KEEP2</ac:parameter></ac:structured-macro>
        </div>
        """

        install_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )
        rollback_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_key="NEW-REL",
            install_rows_html=install_rows_html,
            rollback_rows_html=rollback_rows_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertIn(">NEW-REL</ac:parameter>", merged)
        self.assertIn("app-smart-profile", merged)
        self.assertIn("KEEP2", merged)

    def test_merge_tolerates_template_variations_and_macros(self):
        template_storage = """
        <div>
          <h1><span>Deploy</span> plan: OLD-REL</h1>
          <ac:structured-macro ac:name="info"><ac:parameter ac:name="title">KEEP_INFO</ac:parameter></ac:structured-macro>
          <p>какой-то текст</p>
          <h2>Релиз</h2>
          <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-REL</ac:parameter></ac:structured-macro>
          <h2>План установки</h2>
          <table>
            <tbody>
              <tr>
                <th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>
              </tr>
              <tr><td>1</td><td>Команда</td><td>old-component</td><td>old</td><td></td><td></td></tr>
            </tbody>
          </table>
          <h2>План отката</h2>
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

        install_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )
        rollback_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_key="NEW-REL",
            install_rows_html=install_rows_html,
            rollback_rows_html=rollback_rows_html,
        )
        self.assertIsNotNone(merged)
        assert merged is not None
        self.assertIn(">NEW-REL</ac:parameter>", merged)
        self.assertIn("app-smart-profile", merged)
        self.assertIn("KEEP_AFTER", merged)

    def test_merge_strips_placeholder_service_blocks_in_install_section(self):
        template_storage = """
        <div>
          <h2>Релиз</h2>
          <ac:structured-macro ac:name="jira"><ac:parameter ac:name="key">OLD-REL</ac:parameter></ac:structured-macro>
          <h2>План установки</h2>
          <table><tbody>
            <tr><th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th></tr>
            <tr><td>1</td><td>Команда</td><td>old-component</td><td>old</td><td></td><td></td></tr>
          </tbody></table>
          <table><tbody>
            <tr><th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th></tr>
            <tr><td>1</td><td>Команда</td><td>service</td><td>Update+migration+deploy</td><td>25 февр. 2025 г.</td><td></td></tr>
          </tbody></table>
          <h2>План отката</h2>
          <table><tbody>
            <tr><th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th></tr>
            <tr><td>1</td><td>Команда</td><td>service</td><td>rollback</td><td>25 февр. 2025 г.</td><td></td></tr>
          </tbody></table>
        </div>
        """

        install_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )
        rollback_rows_html = build_component_table_rows(
            ["app-smart-profile"], team_label="Команда", date_text="07 февр. 2025 г."
        )

        merged = merge_deploy_plan_into_template_storage(
            template_storage,
            release_key="NEW-REL",
            install_rows_html=install_rows_html,
            rollback_rows_html=rollback_rows_html,
        )
        assert merged is not None
        self.assertIn("app-smart-profile", merged)
        self.assertNotIn(">service<", merged)


if __name__ == "__main__":
    unittest.main()

