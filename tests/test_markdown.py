from backend.markdown import render_markdown


def test_returns_empty_string_for_falsy_input():
    assert render_markdown(None) == ""
    assert render_markdown("") == ""


def test_renders_basic_markdown():
    out = render_markdown("**hi**")
    assert "<strong>hi</strong>" in out


def test_uses_extra_extension_for_link_text():
    out = render_markdown("[label](https://example.com)")
    assert '<a href="https://example.com">label</a>' in out


def test_sane_lists_keeps_consecutive_lines_in_one_list():
    out = render_markdown("- a\n- b\n- c")
    assert out.count("<li>") == 3
