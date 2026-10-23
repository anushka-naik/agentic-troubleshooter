"""Build and persist the documentation index.

Documents are split on Markdown headers first so that every chunk is a
coherent, citable section ("Doc title > Section"), then long sections are
split further by size.
"""

import json
import logging
import re
from pathlib import Path

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from troubleshooter.config import Settings

logger = logging.getLogger(__name__)

CHUNKS_FILE = "chunks.json"
_SOURCE_LINE = re.compile(r"^Source:\s*(\S+)\s*$", re.MULTILINE)
_HEADERS = [("#", "doc_title"), ("##", "section"), ("###", "subsection")]


def get_embeddings(settings: Settings) -> FastEmbedEmbeddings:
    settings.embedding_cache_dir.mkdir(parents=True, exist_ok=True)
    return FastEmbedEmbeddings(model_name=settings.embedding_model, cache_dir=str(settings.embedding_cache_dir))


def load_chunks(docs_dir: Path) -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS, strip_headers=False)
    size_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150)

    chunks: list[Document] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        sources = _SOURCE_LINE.findall(text)
        body = _SOURCE_LINE.sub("", text)

        sections = size_splitter.split_documents(header_splitter.split_text(body))
        for position, section in enumerate(sections):
            meta = section.metadata
            title = meta.get("doc_title", path.stem)
            heading = meta.get("subsection") or meta.get("section")
            section.metadata = {
                "chunk_id": f"{path.stem}#{position}",
                "doc": path.name,
                "title": f"{title} > {heading}" if heading else title,
                "url": sources[0] if sources else path.name,
            }
            chunks.append(section)
    return chunks


def build_index(settings: Settings) -> int:
    chunks = load_chunks(settings.docs_dir)
    if not chunks:
        raise ValueError(f"No Markdown documents found in {settings.docs_dir}")

    store = FAISS.from_documents(chunks, get_embeddings(settings))
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    store.save_local(str(settings.index_dir))

    serialised = [{"page_content": c.page_content, "metadata": c.metadata} for c in chunks]
    (settings.index_dir / CHUNKS_FILE).write_text(json.dumps(serialised, indent=2), encoding="utf-8")
    logger.info("Indexed %d chunks from %s", len(chunks), settings.docs_dir)
    return len(chunks)


def index_exists(settings: Settings) -> bool:
    return (settings.index_dir / "index.faiss").exists() and (settings.index_dir / CHUNKS_FILE).exists()
