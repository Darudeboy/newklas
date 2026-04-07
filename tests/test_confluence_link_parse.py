from core.confluence_client import ConfluenceClient


def test_extract_page_id_from_viewpage_url() -> None:
    assert (
        ConfluenceClient.extract_page_id(
            "https://confluence.sberbank.ru/pages/viewpage.action?pageId=23285501368"
        )
        == "23285501368"
    )


def test_extract_page_id_from_rest_url() -> None:
    assert (
        ConfluenceClient.extract_page_id(
            "https://confluence.sberbank.ru/rest/api/content/18588013525?expand=body.storage"
        )
        == "18588013525"
    )


def test_extract_page_id_none_for_unrelated_url() -> None:
    assert ConfluenceClient.extract_page_id("https://example.com/foo") is None

