from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_global_typography_is_increased_and_hierarchical():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "font-size: 1.12rem" in source
    assert "font-weight: 500" in source
    assert "h1 {{ font-size: clamp(2rem" in source
    assert "font-weight: 750" in source
    assert "font-size: 1.05rem" in source


def test_classroom_typography_is_increased_without_changing_layout_contract():
    source = (ROOT / "components" / "chat_classroom.py").read_text(encoding="utf-8")
    assert "font-size: 1.12rem" in source
    assert "font-size: 1.7rem" in source
    assert "font-size: 1.12rem !important" in source
    assert 'key=f"{classroom_key}_history"' in source
    assert "height=600" in source
    assert "position: absolute" in source
