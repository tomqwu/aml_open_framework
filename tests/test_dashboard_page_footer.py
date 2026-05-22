"""Source-guard: every dashboard page MUST end with `page_footer()`.

Closes the bottom-page-clip bug systemically. History:
- #305 bumped padding-bottom from 1.5rem → 4rem
- #310 bumped padding-bottom from 4rem → 8rem + added min-height
- ...and the bug came back when new pages shipped with trailing content
  that broke out of the reserved space (download buttons, custom HTML
  iframes, charts with negative margins, etc.).

The systemic fix is three layers — CSS pseudo-element spacer +
visible `page_footer()` affordance + this source-guard test. The test
is the contractual lock: a future page can't ship without the bottom
affordance, so this bug can't regress silently again.

If this test fails, the fix is one line at the end of the page:

    from aml_framework.dashboard.components import page_footer
    # ... rest of the page ...
    page_footer()
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "aml_framework" / "dashboard" / "pages"

# Intentional exemptions — page filenames that legitimately do NOT
# call `page_footer()` (e.g. pages that fully embed an external
# document and have no Streamlit content to be clipped).
#
# Add to this set only with a written reason. Bare "we forgot" entries
# are NOT acceptable — the systemic-fix contract is that every visible
# Streamlit page surface gets the affordance.
EXEMPT_PAGES: set[str] = set()


def _page_files() -> list[Path]:
    return sorted(p for p in PAGES_DIR.glob("*.py") if p.name != "__init__.py")


@pytest.mark.parametrize(
    "page_file",
    _page_files(),
    ids=lambda p: p.name,
)
def test_page_imports_page_footer(page_file: Path) -> None:
    """Every page must import `page_footer` from
    `aml_framework.dashboard.components`."""
    if page_file.name in EXEMPT_PAGES:
        pytest.skip(f"{page_file.name} is exempt — see EXEMPT_PAGES")
    src = page_file.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports_page_footer = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "aml_framework.dashboard.components":
                for alias in node.names:
                    if alias.name == "page_footer":
                        imports_page_footer = True
                        break
    assert imports_page_footer, (
        f"{page_file.name} does not import `page_footer` from "
        "`aml_framework.dashboard.components`. Add the import + call "
        "`page_footer()` as the page's last statement so the bottom-of-page "
        "affordance + 10rem of breathing room render reliably."
    )


@pytest.mark.parametrize(
    "page_file",
    _page_files(),
    ids=lambda p: p.name,
)
def test_page_calls_page_footer(page_file: Path) -> None:
    """Every page must contain a top-level `page_footer()` call.

    Top-level here means: at module scope (not nested inside an `if`/`for`
    block), so the affordance renders unconditionally. A conditional
    call would let the bug regress on whichever code path skipped it.
    """
    if page_file.name in EXEMPT_PAGES:
        pytest.skip(f"{page_file.name} is exempt — see EXEMPT_PAGES")
    src = page_file.read_text(encoding="utf-8")
    tree = ast.parse(src)
    found_top_level_call = False
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == "page_footer":
                found_top_level_call = True
                break
    assert found_top_level_call, (
        f"{page_file.name} does not call `page_footer()` at module scope. "
        "Add `page_footer()` as the page's last top-level statement so the "
        "bottom-of-page affordance renders unconditionally."
    )


def _walk_st_stop_calls(tree: ast.AST) -> list[tuple[ast.Call, list[ast.stmt]]]:
    """Return every `st.stop()` call paired with the statement list it lives in.

    The statement list is what we'd scan to find a preceding `page_footer()`
    call: when stop is inside `if not tunable_rules:`, the body to scan is
    the `if` block's body, not the module's top-level body. That's how we
    correctly require the footer to render on the early-return path.
    """
    out: list[tuple[ast.Call, list[ast.stmt]]] = []

    def walk_body(body: list[ast.stmt]) -> None:
        for node in body:
            # Look for `st.stop()` as an expression-statement in this body.
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                func = call.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "stop"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "st"
                ):
                    out.append((call, body))
            # Recurse into nested bodies (if/for/while/try/with/etc.).
            for attr in ("body", "orelse", "finalbody"):
                inner = getattr(node, attr, None)
                if isinstance(inner, list) and inner and isinstance(inner[0], ast.stmt):
                    walk_body(inner)
            # try/except handlers.
            handlers = getattr(node, "handlers", None)
            if isinstance(handlers, list):
                for h in handlers:
                    if isinstance(h, ast.ExceptHandler):
                        walk_body(h.body)

    walk_body(tree.body)
    return out


@pytest.mark.parametrize(
    "page_file",
    _page_files(),
    ids=lambda p: p.name,
)
def test_st_stop_is_preceded_by_page_footer(page_file: Path) -> None:
    """Every `st.stop()` call must be immediately preceded by a
    `page_footer()` call in the SAME statement block.

    Codex pass on the bottom-page systemic fix:

        "When a page hits an empty-state st.stop() before its final
        page_footer() call, such as Rule Tuning with no
        aggregation_window rules or Alert Queue with no alerts, this
        guard still passes because it only looks for a top-level
        footer call. The footer never renders on those paths..."

    Closing the hole at the test layer so the contract holds for
    empty-state / early-return paths too. Pages that legitimately
    don't need a stop site (most of them) trivially pass — this
    only fires when an `st.stop()` is actually present.
    """
    if page_file.name in EXEMPT_PAGES:
        pytest.skip(f"{page_file.name} is exempt — see EXEMPT_PAGES")
    src = page_file.read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders: list[str] = []
    for stop_call, body in _walk_st_stop_calls(tree):
        # Find the stop's index in its body.
        stop_idx = next(
            (
                i
                for i, n in enumerate(body)
                if isinstance(n, ast.Expr)
                and isinstance(n.value, ast.Call)
                and n.value is stop_call
            ),
            None,
        )
        if stop_idx is None:
            continue
        # Look at the IMMEDIATELY preceding statement. We require the
        # footer to be literally the line above `st.stop()` (not just
        # somewhere earlier in the body) so a casual reader sees the
        # pairing without ambiguity.
        prev = body[stop_idx - 1] if stop_idx > 0 else None
        is_footer_call = (
            prev is not None
            and isinstance(prev, ast.Expr)
            and isinstance(prev.value, ast.Call)
            and isinstance(prev.value.func, ast.Name)
            and prev.value.func.id == "page_footer"
        )
        if not is_footer_call:
            offenders.append(f"line {stop_call.lineno}: st.stop() not preceded by page_footer()")
    assert not offenders, (
        f"{page_file.name}: every `st.stop()` early-return must be preceded by "
        "`page_footer()` so the bottom-page affordance renders on that path. "
        "Offenders:\n  " + "\n  ".join(offenders)
    )


def test_empty_state_helper_renders_footer_before_stop() -> None:
    """`empty_state(stop=True)` must call `page_footer()` before
    `st.stop()` so helper-driven empty-state paths (e.g. Lineage
    Explorer / Information Sharing on direct visit without
    `case_id`) don't skip the bottom-page affordance.

    Codex pass 2 on PR #398. The bare `st.stop()` guard above
    misses this because the stop call lives inside the helper,
    not the page.
    """
    components_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "aml_framework"
        / "dashboard"
        / "components.py"
    )
    src = components_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    target: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "empty_state":
            target = node
            break
    assert target is not None, "expected to find `empty_state` in components.py"
    # Walk the function body, find the `if stop:` block and assert
    # that inside it, `page_footer()` appears before `st.stop()`.
    if_blocks = [n for n in target.body if isinstance(n, ast.If)]
    stop_branch: list[ast.stmt] | None = None
    for if_node in if_blocks:
        # `if stop:` test is a bare Name reference.
        if isinstance(if_node.test, ast.Name) and if_node.test.id == "stop":
            stop_branch = if_node.body
            break
    assert stop_branch is not None, "expected `if stop:` branch in empty_state"
    # Find page_footer + st.stop indices in the branch.
    pf_idx: int | None = None
    stop_idx: int | None = None
    for i, stmt in enumerate(stop_branch):
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            func = stmt.value.func
            if isinstance(func, ast.Name) and func.id == "page_footer":
                pf_idx = i
            elif (
                isinstance(func, ast.Attribute)
                and func.attr == "stop"
                and isinstance(func.value, ast.Name)
                and func.value.id == "st"
            ):
                stop_idx = i
    assert pf_idx is not None, "empty_state(stop=True) branch must call page_footer()"
    assert stop_idx is not None, "empty_state(stop=True) branch must call st.stop()"
    assert pf_idx < stop_idx, (
        "page_footer() must appear BEFORE st.stop() in empty_state(stop=True), "
        f"got page_footer at idx {pf_idx}, st.stop at idx {stop_idx}"
    )


@pytest.mark.parametrize(
    "page_file",
    _page_files(),
    ids=lambda p: p.name,
)
def test_page_footer_is_last_top_level_statement(page_file: Path) -> None:
    """`page_footer()` should be the LAST top-level statement in the
    page. Anything after it would visually appear BELOW the footer,
    which defeats the "you've reached the end of the page" affordance.
    """
    if page_file.name in EXEMPT_PAGES:
        pytest.skip(f"{page_file.name} is exempt — see EXEMPT_PAGES")
    src = page_file.read_text(encoding="utf-8")
    tree = ast.parse(src)
    if not tree.body:
        pytest.fail(f"{page_file.name} appears empty")
    last = tree.body[-1]
    is_page_footer_call = (
        isinstance(last, ast.Expr)
        and isinstance(last.value, ast.Call)
        and isinstance(last.value.func, ast.Name)
        and last.value.func.id == "page_footer"
    )
    assert is_page_footer_call, (
        f"{page_file.name}: the last top-level statement must be "
        "`page_footer()`, not "
        f"{ast.dump(last, annotate_fields=False)[:80]}. Anything after "
        "the footer renders below the 'end of page' affordance."
    )
