"""Hierarchical, structure-aware chunker.

Two-pass strategy:
  1. Consume the loader's block stream and rebuild the section tree by
     watching heading levels. Every non-heading block attaches to the
     current open section.
  2. Within each section, pack prose into token-bounded chunks with
     sentence-boundary-respecting overlap. Tables / code / figure
     captions are kept as atomic chunks even if they exceed the target
     size - splitting them destroys meaning.

Outputs are `Section` + `Chunk` objects; both carry char-offsets and
page numbers so the traceability agent can render "page 412, lines X-Y"
citations at the end.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ai_testplan_generator.config import Settings, get_settings
from ai_testplan_generator.ingestion.loaders import RawBlock
from ai_testplan_generator.llm.tokens import count_tokens
from ai_testplan_generator.models import Chunk, ChunkKind, Document, Section

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_ATOMIC_KINDS = {"table", "code", "formula", "caption"}


@dataclass
class _OpenSection:
    section: Section
    buffer: list[RawBlock]


class HierarchicalChunker:
    """Converts a stream of RawBlocks into (Sections, Chunks)."""

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.target_tokens = s.chunk_target_tokens
        self.overlap_tokens = s.chunk_overlap_tokens

    def chunk(
        self, document: Document, blocks: Iterable[RawBlock]
    ) -> tuple[list[Section], list[Chunk]]:
        sections: list[Section] = []
        chunks: list[Chunk] = []
        stack: list[_OpenSection] = []
        char_cursor = 0

        def close_until(level: int) -> None:
            while stack and stack[-1].section.level >= level:
                open_sec = stack.pop()
                section_chunks = list(
                    self._chunk_section_buffer(document, open_sec.section, open_sec.buffer)
                )
                chunks.extend(section_chunks)

        # Synthetic root section so blocks emitted before any heading are
        # still attached to something traceable.
        root = Section(
            document_id=document.id,
            title=document.title,
            level=1,
            char_start=0,
            char_end=0,
        )
        sections.append(root)
        stack.append(_OpenSection(section=root, buffer=[]))

        for block in blocks:
            text = block.text
            block_char_start = char_cursor
            char_cursor += len(text) + 1  # +1 for implicit newline between blocks

            if block.kind == "heading":
                close_until(block.level)
                section = Section(
                    document_id=document.id,
                    title=text,
                    level=max(1, block.level or 1),
                    parent_id=stack[-1].section.id if stack else None,
                    page_start=block.page,
                    page_end=block.page,
                    char_start=block_char_start,
                    char_end=char_cursor,
                )
                sections.append(section)
                stack.append(_OpenSection(section=section, buffer=[]))
            else:
                stack[-1].buffer.append(block)

        # Close everything still on the stack.
        while stack:
            open_sec = stack.pop()
            chunks.extend(
                self._chunk_section_buffer(document, open_sec.section, open_sec.buffer)
            )

        return sections, chunks

    # -- per-section chunking --------------------------------------------------

    def _chunk_section_buffer(
        self, doc: Document, section: Section, buf: list[RawBlock]
    ) -> Iterator[Chunk]:
        # Separate atomic (table/code/figure) from flowing prose so prose
        # can be packed across adjacent blocks but atomic blocks stay whole.
        prose_buf: list[RawBlock] = []
        for block in buf:
            if block.kind in _ATOMIC_KINDS:
                if prose_buf:
                    yield from self._pack_prose(doc, section, prose_buf)
                    prose_buf = []
                yield self._atomic_chunk(doc, section, block)
            else:
                prose_buf.append(block)
        if prose_buf:
            yield from self._pack_prose(doc, section, prose_buf)

    def _atomic_chunk(self, doc: Document, section: Section, block: RawBlock) -> Chunk:
        kind_map = {
            "table": ChunkKind.TABLE,
            "code": ChunkKind.CODE,
            "formula": ChunkKind.FORMULA,
            "caption": ChunkKind.FIGURE_CAPTION,
        }
        return Chunk(
            document_id=doc.id,
            section_id=section.id,
            kind=kind_map.get(block.kind, ChunkKind.PROSE),
            text=block.text,
            token_count=count_tokens(block.text),
            page_start=block.page,
            page_end=block.page,
            char_start=section.char_start,
            char_end=section.char_end,
            extra={**block.metadata},
        )

    def _pack_prose(
        self, doc: Document, section: Section, blocks: list[RawBlock]
    ) -> Iterator[Chunk]:
        """Pack sentences into token-bounded chunks with sentence-aware overlap."""
        # Flatten to sentence-level units, keeping page numbers per sentence.
        sentences: list[tuple[str, int | None]] = []
        for block in blocks:
            for sent in _split_sentences(block.text):
                if sent.strip():
                    sentences.append((sent.strip(), block.page))

        if not sentences:
            return

        current: list[tuple[str, int | None]] = []
        current_tokens = 0
        for sent, page in sentences:
            sent_tokens = count_tokens(sent)
            if current_tokens + sent_tokens > self.target_tokens and current:
                yield self._build_prose_chunk(doc, section, current)
                current = _tail_overlap(current, self.overlap_tokens)
                current_tokens = sum(count_tokens(s) for s, _ in current)
            current.append((sent, page))
            current_tokens += sent_tokens

        if current:
            yield self._build_prose_chunk(doc, section, current)

    @staticmethod
    def _build_prose_chunk(
        doc: Document, section: Section, sentences: list[tuple[str, int | None]]
    ) -> Chunk:
        text = " ".join(s for s, _ in sentences)
        pages = [p for _, p in sentences if p is not None]
        return Chunk(
            document_id=doc.id,
            section_id=section.id,
            kind=ChunkKind.PROSE,
            text=text,
            token_count=count_tokens(text),
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            char_start=section.char_start,
            char_end=section.char_end,
        )


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    # Long tokens (e.g. raw table rows) slip through the regex without
    # splitting - which is what we want.
    return _SENTENCE_SPLIT.split(text)


def _tail_overlap(
    sentences: list[tuple[str, int | None]], overlap_tokens: int
) -> list[tuple[str, int | None]]:
    if overlap_tokens <= 0 or not sentences:
        return []
    tail: list[tuple[str, int | None]] = []
    tok = 0
    for sent, page in reversed(sentences):
        t = count_tokens(sent)
        if tok + t > overlap_tokens and tail:
            break
        tail.append((sent, page))
        tok += t
    tail.reverse()
    return tail
