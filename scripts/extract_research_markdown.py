#!/usr/bin/env python3
"""Build-time converter: research whitepaper HTML → Markdown data module.

PR-U2 of the unified-product epic. The GitHub-Pages marketing site is
being merged into the product. The 8 Research whitepapers under
``docs/pitch/landing/research/*.html`` are ported into native Streamlit
Knowledge pages.

This script mirrors the established ``dashboard/data/regulator_pulse.py``
discipline: we do NOT parse the source HTML at dashboard runtime
(stability — a marketing-site reflow must not break the dashboard; and
no new mistune / markdown-it dependency on the unit-test CI image).
Instead this one-shot tool extracts the substantive prose into a
committed Python data module that the Knowledge pages render verbatim.

Re-run when a source whitepaper is re-authored:

    python scripts/extract_research_markdown.py

It rewrites ``src/aml_framework/dashboard/data/research.py`` in place.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "pitch" / "landing" / "research"
OUT = ROOT / "src" / "aml_framework" / "dashboard" / "data" / "research.py"

# Stable slug → (numbered page filename suffix, GitHub source markdown).
# The slug matches the source HTML stem so re-extraction is mechanical.
SLUGS = [
    "architecture",
    "competitive-positioning",
    "data-problem",
    "fintech",
    "lineage",
    "process-pain",
    "regulator-pulse",
    "td-2024",
]

# Stable per-whitepaper nav metadata. The HTML <title>/r-title carry
# cosmetic <em> kerning we don't want in the sidebar / tour heading /
# audience-map key, so the human-facing nav title is curated here (and
# pinned by tests/test_dashboard_knowledge.py). Order matches SLUGS.
#
#   slug -> (page_number, nav_title, sidebar_icon)
#
# page_number drives the on-disk filename `33_Knowledge_<Slug>.py`
# (33..40) so the file ordering is stable and the tour-coverage test's
# filename→title derivation stays mechanical via an override map.
NAV = {
    "architecture": (33, "Architecture", ":material/account_tree:"),
    "competitive-positioning": (34, "Competitive Landscape", ":material/insights:"),
    "data-problem": (35, "Data Is The Problem", ":material/database:"),
    "fintech": (36, "FinTech AML Reality", ":material/rocket_launch:"),
    "lineage": (37, "Lineage Deep-Dive", ":material/timeline:"),
    "process-pain": (38, "AML Process Pain", ":material/healing:"),
    "regulator-pulse": (39, "Regulator Pulse Brief", ":material/podcasts:"),
    "td-2024": (40, "TD 2024 Case Study", ":material/gavel:"),
}

# The whitepapers "view source on github" footer points at the canonical
# markdown. Captured so the Knowledge page can offer an "Open the source
# doc" link (parity with the static site's footer affordance). Every
# path here MUST resolve to a real file under docs/ — these mirror the
# `blob/main/...` hrefs the source HTML's own footer emits. The
# `lineage` whitepaper carries no source-doc footer link of its own; we
# point it at the repo doc whose subject it summarises (lineage.html
# itself directs the reader to "Audit & Evidence → Lineage walk-back").
GH_SOURCE = {
    "architecture": "docs/architecture.md",
    "competitive-positioning": "docs/research/2026-04-competitive-positioning.md",
    "data-problem": "docs/research/2026-05-aml-data-problem.md",
    "fintech": "docs/research/2026-04-fintech-aml-reality.md",
    "lineage": "docs/audit-evidence.md",
    "process-pain": "docs/research/2026-04-aml-process-pain.md",
    # Canonical, continuously-maintained edition (sourced from the .md
    # verbatim, not the stale static-site HTML snapshot — see
    # MARKDOWN_SOURCE). 2026-02-01 → 2026-05-08, 32 events.
    "regulator-pulse": "docs/research/2026-05-regulator-pulse.md",
    "td-2024": "docs/case-studies/td-2024.md",
}

# Internal cross-links carried over from the static research site point
# at sibling `<slug>.html` files (e.g. fintech → process-pain.html,
# process-pain → td-2024.html). Inside the dashboard those resolve to
# non-existent `.html` paths, so remap each to its Streamlit page route.
# NAV is the single source of truth. The Streamlit route is NOT the
# numbered file stem — app.py registers these pages with an explicit
# `url_path` equal to the app-wide title→slug convention
# (`nav_title.replace(" & ", "_").replace(" ", "_")`; hyphens preserved,
# see tests/test_e2e_dashboard.py:257 and app.py's Knowledge block). The
# generated render_body footer below uses the identical transform.
# Source HTML stem == slug.
INTERNAL_LINK_MAP = {
    f"{slug}.html": "./" + nav_title.replace(" & ", "_").replace(" ", "_")
    for slug, (_page_no, nav_title, _icon) in NAV.items()
}

_INLINE_KEEP = {"strong", "b", "em", "i", "code", "a"}

# HTML void elements never get an end tag — they must not push onto the
# tag stack or bump the skip-depth counter (the original bug: <link> /
# <meta> inside <head> incremented skip_depth with no matching decrement,
# so the parser skipped the entire <body>).
_VOID = {"meta", "link", "br", "img", "hr", "input", "source", "area", "base", "col"}


def _clean_ws(text: str) -> str:
    return re.sub(r"[ \t]*\n[ \t]*", " ", re.sub(r"\s+", " ", text)).strip()


_MARK = {"strong": "**", "b": "**", "em": "*", "i": "*", "code": "`"}


class _Inline:
    """Accumulates an inline run as a token tree.

    Formatting spans are tracked structurally rather than as raw `**`
    text. A span whose textual content is whitespace-only is dropped
    entirely — the whitepapers use empty `<em></em>` / `<strong> </strong>`
    purely for typographic kerning, and naive `**`-injection produced
    invalid Markdown (unbalanced or accidentally-merged emphasis). This
    structural model means real adjacent bold ("**A** then **B**") and
    glued bold ("**program**jurisdiction") both survive untouched.
    """

    class _Span:
        __slots__ = ("mark", "href", "children")

        def __init__(self, mark: str, href: str | None = None) -> None:
            self.mark = mark  # "**" / "*" / "`" / "" (link) / None (root)
            self.href = href
            self.children: list[object] = []  # str | _Span

    def __init__(self) -> None:
        self._root = self._Span(None)
        self._stack = [self._root]

    def open(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == "br":
            self._stack[-1].children.append(" ")
            return
        if tag == "a":
            span = self._Span("", href=attrs.get("href"))
        elif tag in _MARK:
            span = self._Span(_MARK[tag])
        else:
            return
        self._stack[-1].children.append(span)
        self._stack.append(span)

    def close(self, tag: str) -> None:
        if tag in _MARK or tag == "a":
            if len(self._stack) > 1:
                self._stack.pop()

    def text(self, data: str) -> None:
        self._stack[-1].children.append(data)

    def _emit(self, node: "_Inline._Span") -> str:
        inner = "".join(c if isinstance(c, str) else self._emit(c) for c in node.children)
        if node.mark is None:  # root
            return inner
        if not inner.strip():  # empty kerning span — drop the markers
            return inner if inner else ""
        if node.mark == "":  # link
            href = node.href or ""
            # Remap internal static-site cross-links to the native
            # Streamlit page route (external URLs pass through).
            href = INTERNAL_LINK_MAP.get(href, href)
            return f"[{inner}]({href})" if href else inner
        # Markdown emphasis can't wrap leading/trailing whitespace.
        lead = inner[: len(inner) - len(inner.lstrip())]
        trail = inner[len(inner.rstrip()) :]
        core = inner.strip()
        return f"{lead}{node.mark}{core}{node.mark}{trail}"

    def render(self) -> str:
        raw = _clean_ws(self._emit(self._root))
        # Tidy any space the structural drop left before punctuation.
        return re.sub(r"\s+([.,;:!?])", r"\1", raw)


class WhitepaperParser(HTMLParser):
    """Recursive-descent HTML → Markdown for the r-* whitepaper schema.

    The whitepapers use a small, consistent vocabulary of semantic
    classes (r-h2, r-p, r-list, r-table, r-callout, plus bespoke layout
    wrappers like r-event / r-card / r-row). Layout wrappers are
    transparent — we recurse into them and emit their headings / prose
    in document order. Decorative chrome (r-frame, r-foot, r-meta, the
    arch SVG arrows) is dropped.
    """

    # Block-level class → markdown emitter mode.
    SKIP_BLOCKS = {"r-frame", "r-foot", "r-meta", "arch-flow", "r-sources"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.title: str = ""
        self.eyebrow: str = ""
        self.lede: str = ""
        self._mode: str | None = None
        self._inline: _Inline | None = None
        # Tag-stack depth at which the active inline block opened. The
        # block flushes only when we pop back to (or above) that depth —
        # decorative <span>/<div> kerning wrappers inside a heading must
        # NOT prematurely terminate it (the "## 1." truncation bug).
        self._block_depth: int | None = None
        # The open tag-name of the active `.label`/`.lead` bold kicker
        # (so the matching end tag — span OR div — closes it), else None.
        self._label_open: str | None = None
        self._skip_depth = 0
        self._tag_stack: list[str] = []
        # list handling — parallel stacks of kind ("ul"/"ol") and the
        # running counter for ordered lists.
        self._list_stack: list[str] = []
        self._list_counter: list[int] = []
        self._li_inline: _Inline | None = None
        # table handling
        self._in_table = False
        self._table_rows: list[list[str]] = []
        self._table_is_head: list[bool] = []
        self._cur_row: list[str] | None = None
        self._cell_inline: _Inline | None = None
        self._row_is_head = False
        # row-key / row-val pair handling
        self._pending_key: str | None = None

    # -- helpers ----------------------------------------------------
    def _class(self, attrs: list[tuple[str, str | None]]) -> str:
        for k, v in attrs:
            if k == "class":
                return v or ""
        return ""

    def _attrs_dict(self, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {k: (v or "") for k, v in attrs}

    def _flush_inline(self) -> None:
        if self._inline is None:
            return
        text = self._inline.render()
        mode = self._mode
        self._inline = None
        self._mode = None
        if not text:
            return
        if mode == "title":
            self.title = text
        elif mode == "eyebrow":
            self.eyebrow = text
        elif mode == "lede":
            self.lede = text
        elif mode == "h2":
            self.blocks.append(f"## {text}")
        elif mode == "h3":
            self.blocks.append(f"### {text}")
        elif mode == "h4":
            # Load-bearing labels above their list (Competitive
            # Landscape "Strengths"/"Cautions"; the data-problem /
            # process-pain "Use these"/"Avoid these" style headers).
            # Dropping these merged opposite lists under no heading.
            self.blocks.append(f"#### {text}")
        elif mode == "label":
            # r-event-date / card-tag / archetype — a small bold kicker.
            self.blocks.append(f"**{text}**")
        elif mode == "badges":
            # The two `.badge` spans glue with no separator in source
            # (CSS gap). Restore a readable separator before the
            # IMPACT/EFFORT badge — same glue-repair idiom as the
            # arch-diagram bullet below. Rendered bold as a kicker line.
            text = re.sub(r"(?<=\S)(IMPACT/EFFORT:)", r" · \1", text)
            self.blocks.append(f"**{text}**")
        elif mode == "rowkey":
            self._pending_key = text
        elif mode == "rowval":
            if self._pending_key:
                self.blocks.append(f"**{self._pending_key}** — {text}")
                self._pending_key = None
            else:
                self.blocks.append(text)
        elif mode == "bullet":
            # The arch diagram's .item glues "<strong>name</strong>desc"
            # with no space (CSS made strong display:block). Restore a
            # readable separator so the bullet renders as "name — desc".
            text = re.sub(r"^(\*\*[^*]+\*\*)(?=\S)", r"\1 — ", text)
            self.blocks.append(f"- {text}")
        elif mode == "callout":
            self.blocks.append("> " + text.replace("\n", "\n> "))
        else:  # paragraph / dek
            self.blocks.append(text)

    # -- HTMLParser hooks -------------------------------------------
    def handle_starttag(self, tag: str, attrs):  # noqa: D102
        cls = self._class(attrs)
        adict = self._attrs_dict(attrs)

        # Void elements (meta/link/br/img/hr/...) never close; treat as
        # start-end so they neither stack nor distort skip-depth.
        if tag in _VOID:
            self.handle_startendtag(tag, attrs)
            return

        self._tag_stack.append(tag)

        if self._skip_depth:
            self._skip_depth += 1
            return

        if tag in ("script", "style", "svg", "head"):
            self._skip_depth = 1
            return
        if any(c in self.SKIP_BLOCKS for c in cls.split()):
            self._skip_depth = 1
            return

        # A callout/event/source `.label` span — or an r-spa `.lead`
        # div — is a bold kicker leading its body prose. Emit bold
        # markers around it so "Reading note Foo" reads as
        # "**Reading note** Foo" (and the r-spa kicker stays attached to
        # its assumption text in the SAME paragraph) rather than the
        # text running together or the body being dropped.
        if {"label", "lead"} & set(cls.split()) and self._inline is not None:
            self._inline.text(" ")
            self._inline.open("strong", {})
            self._label_open = tag
            return

        # Active inline run — nested formatting tag.
        if self._inline is not None and tag in _INLINE_KEEP | {"br"}:
            self._inline.open(tag, adict)
            return
        if self._li_inline is not None and tag in _INLINE_KEEP | {"br"}:
            self._li_inline.open(tag, adict)
            return
        if self._cell_inline is not None and tag in _INLINE_KEEP | {"br"}:
            self._cell_inline.open(tag, adict)
            return

        # Tables.
        if tag == "table":
            self._in_table = True
            self._table_rows = []
            self._table_is_head = []
            return
        if self._in_table:
            if tag == "tr":
                self._cur_row = []
                self._row_is_head = False
            elif tag in ("td", "th"):
                self._cell_inline = _Inline()
                if tag == "th":
                    self._row_is_head = True
            return

        # Lists.
        if tag in ("ul", "ol"):
            self._list_stack.append(tag)
            self._list_counter.append(0)
            return
        if tag == "li":
            self._li_inline = _Inline()
            return

        # Block starters — only when not already mid-inline.
        if tag == "h1" or "r-title" in cls.split():
            self._start("title")
        elif "r-eyebrow" in cls.split():
            self._start("eyebrow")
        elif "r-lede" in cls.split():
            self._start("lede")
        elif tag == "h2" or {"r-h2", "r-block-h"} & set(cls.split()):
            self._start("h2")
        elif tag == "h3" or {"card-title", "ttl"} & set(cls.split()):
            # r-feat `.ttl` — the feature NAME line. Treated as a
            # subheading so the Competitive Landscape "next features"
            # cards render their name above the body (the cards were
            # otherwise 5 unlabelled paragraphs — content lost).
            self._start("h3")
        elif tag == "h4":
            self._start("h4")
        elif {"r-event-date", "card-tag", "archetype", "rank"} & set(cls.split()):
            # Small bold kickers: r-event-date / card-tag / archetype,
            # plus r-feat `.rank` (#1..#5) — same transparent-wrapper-
            # drop class as the round-1 h4 gap.
            self._start("label")
        elif "badges" in cls.split():
            # r-feat `.badges` — two adjacent `.badge` spans (effort,
            # then impact) with NO whitespace between them in source
            # (CSS gap). Captured as a paragraph; a separator is
            # restored on flush so "3 days" and "IMPACT/EFFORT: HIGH"
            # don't glue (same glue class as the arch-diagram bullet).
            self._start("badges")
        elif {"risk", "r-spa", "vendors"} & set(cls.split()):
            # r-feat `.risk` caveat; r-spa body prose (direct text of
            # the wrapper, no inner <p>; its `.lead` is an inline bold
            # kicker handled below); and r-vendor `.vendors` — the
            # concrete vendor list naming each competitive archetype
            # ("NICE Actimize SAM · Oracle FCCM · ...") which was
            # dropped, leaving each archetype unattributed. Captured as
            # paragraphs so the card's substance survives. Chrome stays
            # excluded: all site chrome is r-frame / r-meta / r-foot
            # (SKIP_BLOCKS) and decorative chart labels (qcorner /
            # qdot-label) are NOT whitelisted, so they remain dropped.
            self._start("paragraph")
        elif "name" in cls.split() and "head" not in cls.split():
            # arch-layer .head .name — the layer's title line.
            self._start("h3")
        elif {"role", "sub"} & set(cls.split()):
            # arch-persona .role / arch-layer .head .sub — context line.
            self._start("paragraph")
        elif "what" in cls.split() or "item" in cls.split():
            # arch-persona .what / arch-layer .items .item — bullet it.
            self._start("bullet")
        elif "row-key" in cls.split():
            self._start("rowkey")
        elif "row-val" in cls.split():
            self._start("rowval")
        elif "r-callout" in cls.split():
            self._start("callout")
        elif tag == "p" or {
            "r-p",
            "r-section-dek",
            "r-block-dek",
            "r-event-what",
            "r-event-impact",
            "r-event-source",
        } & set(cls.split()):
            self._start("paragraph")

    def _start(self, mode: str) -> None:
        # A new block boundary flushes any open inline run first.
        self._flush_inline()
        self._mode = mode
        self._inline = _Inline()
        # The opening tag was just pushed in handle_starttag, so the
        # current depth IS this block's depth.
        self._block_depth = len(self._tag_stack)

    def handle_startendtag(self, tag, attrs):  # noqa: D102
        if tag == "br":
            if self._inline is not None:
                self._inline.text(" ")
            elif self._li_inline is not None:
                self._li_inline.text(" ")

    def handle_endtag(self, tag: str):  # noqa: D102
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()

        if self._skip_depth:
            self._skip_depth -= 1
            return

        if self._label_open == tag and self._inline is not None:
            self._inline.close("strong")
            self._inline.text(" ")
            self._label_open = None
            return
        if self._cell_inline is not None and tag in _INLINE_KEEP | {"br"}:
            self._cell_inline.close(tag)
            return
        if self._li_inline is not None and tag in _INLINE_KEEP | {"br"}:
            self._li_inline.close(tag)
            return
        if self._inline is not None and tag in _INLINE_KEEP | {"br"}:
            self._inline.close(tag)
            return

        # Tables.
        if self._in_table:
            if tag in ("td", "th") and self._cell_inline is not None:
                if self._cur_row is not None:
                    self._cur_row.append(self._cell_inline.render())
                self._cell_inline = None
                return
            if tag == "tr" and self._cur_row is not None:
                self._table_rows.append(self._cur_row)
                self._table_is_head.append(self._row_is_head)
                self._cur_row = None
                return
            if tag == "table":
                self._emit_table()
                self._in_table = False
                return
            return

        if tag == "li" and self._li_inline is not None:
            depth = max(0, len(self._list_stack) - 1)
            indent = "  " * depth
            kind = self._list_stack[-1] if self._list_stack else "ul"
            if kind == "ol" and self._list_counter:
                self._list_counter[-1] += 1
                bullet = f"{self._list_counter[-1]}."
            else:
                bullet = "-"
            text = self._li_inline.render()
            if text:
                self.blocks.append(f"{indent}{bullet} {text}")
            self._li_inline = None
            return
        if tag in ("ul", "ol") and self._list_stack:
            self._list_stack.pop()
            if self._list_counter:
                self._list_counter.pop()
            return

        # Block close — flush only when the element that OPENED the
        # active block has itself closed (stack popped to above the
        # block's depth). Decorative inner <span>/<div> wrappers pop to
        # a deeper level and must not terminate the heading/paragraph.
        if (
            self._inline is not None
            and self._block_depth is not None
            and len(self._tag_stack) < self._block_depth
        ):
            self._flush_inline()
            self._block_depth = None

    def handle_data(self, data: str):  # noqa: D102
        if self._skip_depth:
            return
        if self._cell_inline is not None:
            self._cell_inline.text(data)
        elif self._li_inline is not None:
            self._li_inline.text(data)
        elif self._inline is not None:
            self._inline.text(data)

    def _emit_table(self) -> None:
        if not self._table_rows:
            return
        # Header = first row flagged as <th>, else synthesize a blank one.
        head_idx = next(
            (i for i, h in enumerate(self._table_is_head) if h),
            None,
        )
        if head_idx is None:
            ncol = max(len(r) for r in self._table_rows)
            header = [""] * ncol
            body = self._table_rows
        else:
            header = self._table_rows[head_idx]
            body = [
                r
                for i, r in enumerate(self._table_rows)
                if i != head_idx and not self._table_is_head[i]
            ]
        ncol = len(header)
        lines = [
            "| " + " | ".join(c.replace("|", "\\|") for c in header) + " |",
            "| " + " | ".join(["---"] * ncol) + " |",
        ]
        for row in body:
            cells = (row + [""] * ncol)[:ncol]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        self.blocks.append("\n".join(lines))


def _join_blocks(blocks: list[str]) -> str:
    """Join emitted blocks, keeping list items tight but prose spaced."""
    out: list[str] = []
    prev_is_list = False
    for b in blocks:
        is_list = bool(re.match(r"^\s*(-|\d+\.) ", b))
        if out and not (is_list and prev_is_list):
            out.append("")
        out.append(b)
        prev_is_list = is_list
    return "\n".join(out).strip()


# A handful of whitepapers have a canonical, continuously-maintained
# Markdown edition under docs/research/ that supersedes the (now stale)
# static-site HTML snapshot. Those are sourced from the .md VERBATIM —
# this is regulatory event data, so it is copied byte-for-byte (only the
# H1/lede are split off the front and the Knowledge-page internal links
# remapped); nothing is transcribed, summarised, or invented. The .md is
# already Markdown so the HTML→md machinery is bypassed entirely.
#
#   slug -> canonical markdown path (must equal GH_SOURCE[slug])
MARKDOWN_SOURCE = {
    "regulator-pulse": "docs/research/2026-05-regulator-pulse.md",
}


GH_BASE = "https://github.com/tomqwu/aml_open_framework/blob/main/"


def _remap_md_links(md: str, source_doc: str) -> str:
    """Remap links in a Markdown body sourced from a repo doc.

    Two rewrites, mirroring the HTML path's link discipline so a
    `.md`-sourced page never emits a dead in-app route:

    1. Knowledge-page internal links (``process-pain.html`` etc.) ->
       the native Streamlit route (``INTERNAL_LINK_MAP``).
    2. Relative ``.md`` links carried from the source doc (e.g. the
       "Previous edition" sibling pointer ``2026-04-regulator-pulse.md``)
       -> the absolute GitHub blob URL, resolved against the source
       doc's own directory. Without this they resolve against Streamlit
       (``/2026-04-regulator-pulse.md`` — a dead route).

    Absolute URLs (``http(s)://``), in-page anchors (``#...``), and the
    already-correct internal Knowledge remaps are left untouched.
    """
    src_dir = PurePosixPath(source_doc).parent

    def _sub(m: re.Match[str]) -> str:
        text, target = m.group(1), m.group(2)
        if target in INTERNAL_LINK_MAP:
            return f"[{text}]({INTERNAL_LINK_MAP[target]})"
        # Relative .md pointer (no scheme, not an anchor, not already a
        # Streamlit route): resolve against the source doc dir, absolutise.
        if (
            target.endswith(".md")
            and "://" not in target
            and not target.startswith(("#", "/", "./"))
        ):
            resolved = (src_dir / target).as_posix()
            return f"[{text}]({GH_BASE}{resolved})"
        return f"[{text}]({target})"

    return re.sub(r"\[([^\]]*)\]\(([^)]+)\)", _sub, md)


def _extract_from_markdown(slug: str) -> dict[str, object]:
    """Build the substrate record from the canonical Markdown verbatim.

    Splits the leading `# H1` (-> display_title) and the first prose
    paragraph after it (-> lede); everything from the second paragraph
    on is the body, copied unchanged. The eyebrow is a verbatim
    substring of the .md's own H1 (the title text before its first
    comma) — no number, window, or event count is ever fabricated; the
    .md's own header/lede carry the authoritative window + event count.
    """
    page_no, nav_title, icon = NAV[slug]
    raw = (ROOT / MARKDOWN_SOURCE[slug]).read_text(encoding="utf-8")
    lines = raw.split("\n")
    # Line 0 is the H1 title (the canonical .md starts with `# ...`).
    h1 = lines[0]
    title = h1[1:].strip() if h1.startswith("# ") else h1.strip()
    # First non-empty paragraph after the H1 is the lede; the body is
    # everything from the next paragraph onward, verbatim.
    rest = "\n".join(lines[1:]).lstrip("\n")
    parts = rest.split("\n\n", 1)
    lede = parts[0].strip()
    body = parts[1] if len(parts) > 1 else ""
    # Eyebrow: the .md title text before its first comma — a verbatim
    # slice of the source, so zero fabrication.
    eyebrow = title.split(",", 1)[0].strip()
    return {
        "slug": slug,
        "page_no": page_no,
        "nav_title": nav_title,
        "icon": icon,
        "display_title": title or nav_title,
        "eyebrow": eyebrow,
        "lede": lede,
        "body_md": _remap_md_links(body, MARKDOWN_SOURCE[slug]).strip(),
        "gh_source": GH_SOURCE[slug],
    }


def extract(slug: str) -> dict[str, object]:
    if slug in MARKDOWN_SOURCE:
        return _extract_from_markdown(slug)
    html = (SRC / f"{slug}.html").read_text(encoding="utf-8")
    p = WhitepaperParser()
    p.feed(html)
    p._flush_inline()
    page_no, nav_title, icon = NAV[slug]
    # The source <title> kerning markers (cosmetic *italics*) are kept
    # for the in-page hero subtitle but stripped for any nav surface.
    display_title = re.sub(r"\*+", "", p.title).strip()
    return {
        "slug": slug,
        "page_no": page_no,
        "nav_title": nav_title,
        "icon": icon,
        "display_title": display_title or nav_title,
        "eyebrow": p.eyebrow,
        "lede": p.lede,
        "body_md": _join_blocks(p.blocks),
        "gh_source": GH_SOURCE[slug],
    }


def main() -> None:
    records = [extract(s) for s in SLUGS]
    lines: list[str] = [
        '"""Research whitepapers — extracted prose for the Knowledge section.',
        "",
        "PR-U2 of the unified-product epic. The GitHub-Pages marketing site",
        "is being merged into the product so the GH page can be retired.",
        "The 8 Research whitepapers that lived at",
        "``docs/pitch/landing/research/*.html`` are ported here as native",
        "Streamlit Knowledge pages (``pages/33_Knowledge_*.py``).",
        "",
        "This module is the dashboard-side substrate, generated by",
        "``scripts/extract_research_markdown.py``. We deliberately do NOT",
        "parse the source HTML at runtime — same rationale as",
        "``regulator_pulse.py``: stability (a marketing reflow must not",
        "break the dashboard) and no new markdown-parser dependency on the",
        "unit-test CI image. Re-run the extractor when a whitepaper is",
        "re-authored.",
        "",
        "Each record is prose only — nav chrome, CSS, decorative SVG, and",
        "the back-to-hub frame are stripped. Bespoke diagram blocks that",
        "carried no prose (none in the current set) would degrade to a",
        "short framing line; every current whitepaper is prose-complete.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f"GH_BASE = {GH_BASE!r}",
        "",
        "# slug -> whitepaper record. Insertion order IS the Knowledge nav",
        "# order. Each record:",
        "#   page_no       int   -> on-disk filename 33_Knowledge_*.py",
        "#   nav_title     str   -> sidebar + page_header + tour heading",
        "#   icon          str   -> sidebar material icon",
        "#   display_title str   -> in-page hero h1 (page_header title)",
        "#   eyebrow       str   -> hero kicker (mirrors the static site)",
        "#   lede          str   -> hero standfirst paragraph",
        "#   gh_source     str   -> canonical markdown path on GitHub",
        "#   body_md       str   -> the extracted prose, rendered verbatim",
        "WHITEPAPERS: dict[str, dict[str, str]] = {",
    ]
    for r in records:
        lines.append(f"    {r['slug']!r}: {{")
        lines.append(f'        "page_no": {r["page_no"]!r},')
        lines.append(f'        "nav_title": {r["nav_title"]!r},')
        lines.append(f'        "icon": {r["icon"]!r},')
        lines.append(f'        "display_title": {r["display_title"]!r},')
        lines.append(f'        "eyebrow": {r["eyebrow"]!r},')
        lines.append(f'        "lede": {r["lede"]!r},')
        lines.append(f'        "gh_source": {r["gh_source"]!r},')
        lines.append('        "body_md": (')
        for chunk in r["body_md"].split("\n"):
            lines.append(f"            {chunk + chr(10)!r}")
        lines.append("        ),")
        lines.append("    },")
    lines.append("}")
    lines.append("")
    # Thin render helper baked into the generated module. The Knowledge
    # page scripts are 2-liners that delegate here. Streamlit is
    # imported lazily INSIDE the function so this module stays
    # import-safe on the unit-test CI image (no streamlit there) — same
    # lazy-import contract as audience.py / data_layer.py.
    lines.extend(
        [
            "",
            "def render_body(slug: str) -> None:",
            '    """Render one whitepaper body beneath the page hero.',
            "",
            "    The Knowledge page script owns the ``page_header(...)`` call",
            "    with a LITERAL nav title (the title-mining contract in",
            "    tests/test_dashboard_workflows.py needs the literal so the",
            "    AUDIENCE_PAGES key resolves). Beneath that deck-DNA chrome",
            "    this helper renders the whitepaper's REAL hero — exactly the",
            "    static site's hierarchy: eyebrow kicker -> display_title",
            "    headline -> lede standfirst -> extracted Markdown body ->",
            "    see-also footer. Without the headline/eyebrow each brief",
            "    silently lost its true title (e.g. Architecture's",
            '    "One Manifest. Four layers. No drift."). All 8 pages stay',
            "    4-line scripts with zero copy-pasted prose.",
            "",
            "    Pure prose: no engine / session-state coupling — these are",
            "    reference pages, not run views (documented in the",
            "    STATIC_PAGES exemption set, mirroring 27_Regulator_Pulse.py).",
            '    """',
            "    import streamlit as st",
            "",
            "    from aml_framework.dashboard.components import (",
            "        glossary_legend,",
            "        see_also_footer,",
            "    )",
            "",
            "    wp = WHITEPAPERS[slug]",
            '    if wp["eyebrow"]:',
            "        st.caption(wp['eyebrow'])",
            '    if wp["display_title"]:',
            "        st.markdown(f\"## {wp['display_title']}\")",
            '    if wp["lede"]:',
            "        st.markdown(f\"#### {wp['lede']}\")",
            '    st.markdown(wp["body_md"])',
            "    see_also_footer(",
            "        [",
            '            f"[Open the source doc on GitHub \\u2197]"',
            "            f\"({GH_BASE}{wp['gh_source']})\",",
            '            "[Knowledge index \\u2014 Architecture brief]"',
            '            "(./Architecture)",',
            "        ]",
            "    )",
            "    st.markdown(",
            '        glossary_legend(["MLRO", "STR", "SAR", "FinCEN", "FATF", "AMLA", "FCA"]),',
            "        unsafe_allow_html=True,",
            "    )",
            "",
        ]
    )
    OUT.write_text("\n".join(lines), encoding="utf-8")
    # Normalise with ruff so re-running the extractor is idempotent and
    # the committed module always satisfies `ruff format --check` /
    # `ruff check` (line length 100). Best-effort: skip if ruff absent.
    import subprocess
    import sys

    for cmd in (
        [sys.executable, "-m", "ruff", "format", str(OUT)],
        [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", str(OUT)],
    ):
        try:
            subprocess.run(cmd, check=False, capture_output=True)  # noqa: S603
        except OSError:
            break
    for r in records:
        print(
            f"{r['slug']:24s} #{r['page_no']} {r['nav_title']:24s} body={len(r['body_md'])} chars"
        )


if __name__ == "__main__":
    main()
