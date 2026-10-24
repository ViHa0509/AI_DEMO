from app.knowledge_base import load_docs_from_excel


def test_excel_is_loaded_without_template_or_nan():
    docs = load_docs_from_excel()
    assert len(docs) > 100
    sheets = {d.metadata["sheet"] for d in docs}
    assert "Template" not in sheets
    assert {"Python", "AI", "RPA"} <= sheets
    assert all("nan" not in d.metadata.values() for d in docs)
    assert all(d.page_content.startswith(d.metadata["skill"]) for d in docs)
