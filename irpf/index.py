# The manual in Chroma, two ways:
# - questions: one node per question, long answers split under it, each part headed by its question
# - pages: the baseline, fixed-size chunks over the page text that know nothing about questions
# Embeddings come from a local multilingual model by default. Gemini's free tier allows only 1000
# embedding requests a day, each text counting as one, which doesn't cover the 1,925 nodes, let
# alone the queries; IRPF_EMBED_MODEL=gemini-embedding-001 still works for a comparison. Embeddings
# go through a cache on disk either way, so rebuilding an index or loading the same nodes into
# Pinecone doesn't embed them again.
#
# Usage: uv run python -m irpf.index [--rebuild]

import functools
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import chromadb
import numpy as np
from dotenv import load_dotenv
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, Document, MetadataMode, NodeWithScore, QueryBundle, TextNode
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from pypdf import PdfReader

from irpf import manual

load_dotenv(".env")

EMBED_MODEL = os.environ.get("IRPF_EMBED_MODEL", "intfloat/multilingual-e5-base")
GEMINI = EMBED_MODEL.startswith("gemini")
SLUG = EMBED_MODEL.split("/")[-1]
STORAGE = Path("storage")
CHUNK_SIZE = 512  # tokens; e5 truncates past its own 512, which cuts the tail off a few chunks
CHUNK_OVERLAP = 64
CORPORA = ("questions", "pages")
TOKENS_PER_MINUTE = 25_000  # the free tier allows 30K embedding tokens a minute


def question_nodes(questions: dict[int, manual.Question]) -> list[TextNode]:
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = []
    for q in questions.values():
        head = f"{q.number:03d} — {q.question}"
        parts = splitter.split_text_metadata_aware(q.answer, head)
        for i, part in enumerate(parts):
            nodes.append(
                TextNode(
                    id_=f"q{q.number:03d}-{i}",
                    text=f"{head}\n{part}",
                    # Chroma takes only scalars, so the cross-references are a string
                    metadata={"number": q.number, "chapter": q.chapter, "topic": q.topic, "see": " ".join(map(str, q.see)), "page": q.page, "part": i, "parts": len(parts)},
                    excluded_embed_metadata_keys=["number", "see", "page", "part", "parts"],
                    excluded_llm_metadata_keys=["see", "page", "part", "parts"],
                )
            )
    return nodes


def page_nodes(pdf: Path = manual.PDF) -> list[TextNode]:
    pages = [(i, page.extract_text()) for i, page in enumerate(PdfReader(pdf).pages[manual.FIRST_PAGE - 1 :], start=manual.FIRST_PAGE)]
    text, starts = "", []
    for number, page in pages:
        starts.append((len(text), number))
        text += page + "\n"
    # Question headings in order, to tell which questions a chunk covers (for scoring only)
    headings, expected = [], 1
    for m in re.finditer(r"^\s*(\d{3})\s*[—–-]", text, re.M):
        if int(m[1]) == expected:
            headings.append((m.start(), expected))
            expected += 1
    chunks = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP).get_nodes_from_documents([Document(text=text)])
    nodes = []
    for i, chunk in enumerate(chunks):
        start, end = chunk.start_char_idx, chunk.end_char_idx
        numbers = [n for at, n in headings if at <= start][-1:] + [n for at, n in headings if start < at < end]
        page = [p for at, p in starts if at <= start][-1]
        nodes.append(
            TextNode(
                id_=f"p{i:04d}",
                text=chunk.text,
                metadata={"numbers": " ".join(map(str, numbers)), "page": page},
                excluded_embed_metadata_keys=["numbers", "page"],
                excluded_llm_metadata_keys=["numbers"],
            )
        )
    return nodes


def nodes(corpus: str) -> list[TextNode]:
    return question_nodes(manual.load()) if corpus == "questions" else page_nodes()


@functools.cache
def embed_model() -> BaseEmbedding:
    if GEMINI:
        # No retries inside: EmbeddingCache waits out the free tier's per-minute quota itself
        return GoogleGenAIEmbedding(model_name=EMBED_MODEL, embed_batch_size=100, retries=1)
    # The e5 models are trained with these prefixes
    return HuggingFaceEmbedding(model_name=EMBED_MODEL, query_instruction="query: ", text_instruction="passage: ", embed_batch_size=32, max_length=512)


class EmbeddingCache:
    """Embeddings by model, kind (document or query) and text, in one .npz file"""

    def __init__(self, path: Path = STORAGE / f"embeddings-{SLUG}.npz"):
        self.path = path
        self.vectors: dict[str, np.ndarray] = {}
        if path.exists():
            data = np.load(path)
            self.vectors = dict(zip(data["keys"].tolist(), data["vectors"]))

    @staticmethod
    def key(kind: str, text: str) -> str:
        return hashlib.sha1(f"{kind}\n{text}".encode()).hexdigest()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, keys=np.array(list(self.vectors)), vectors=np.stack(list(self.vectors.values())))

    def embed(self, texts: list[str], kind: str = "document") -> list[list[float]]:
        model = embed_model()
        missing = list(dict.fromkeys(t for t in texts if self.key(kind, t) not in self.vectors))
        if not GEMINI and missing:
            vectors = model.get_text_embedding_batch(missing, show_progress=len(missing) > 100) if kind == "document" else [model.get_query_embedding(t) for t in missing]
            self.vectors.update((self.key(kind, t), np.asarray(v, dtype=np.float32)) for t, v in zip(missing, vectors))
            self.save()
        done, window = len(missing) if not GEMINI else 0, []  # (time, estimated tokens) of the last minute's calls
        while done < len(missing):
            # Batches of up to 100 texts and about 8K tokens (Portuguese runs about 3 characters a token)
            batch, tokens = [], 0
            for text in missing[done : done + 100]:
                if batch and tokens + len(text) / 3 > 8000:
                    break
                batch.append(text)
                tokens += len(text) / 3
            window = [(at, n) for at, n in window if time.time() - at < 60]
            if sum(n for _, n in window) + tokens > TOKENS_PER_MINUTE:
                time.sleep(60 - (time.time() - window[0][0]) + 1)
                continue
            try:
                vectors = model.get_text_embedding_batch(batch) if kind == "document" else [model.get_query_embedding(t) for t in batch]
            except Exception as error:
                # The free tier's per-minute quota, if the estimate fell short: wait it out
                if "RESOURCE_EXHAUSTED" not in repr(error) + repr(error.__cause__) + str(getattr(error, "last_attempt", "")):
                    raise
                print("rate limited, waiting 60s", flush=True)
                time.sleep(60)
                continue
            window.append((time.time(), tokens))
            for text, vector in zip(batch, vectors):
                self.vectors[self.key(kind, text)] = np.asarray(vector, dtype=np.float32)
            self.save()
            done += len(batch)
            print(f"embedded {done}/{len(missing)}", flush=True)
        return [self.vectors[self.key(kind, t)].tolist() for t in texts]


def embed_nodes(items: list[BaseNode], cache: EmbeddingCache) -> None:
    texts = [n.get_content(metadata_mode=MetadataMode.EMBED) for n in items]
    for node, vector in zip(items, cache.embed(texts)):
        node.embedding = vector


def chroma(corpus: str, rebuild: bool = False) -> VectorStoreIndex:
    """The corpus's index in Chroma on disk, built the first time"""
    client = chromadb.PersistentClient(path=str(STORAGE / "chroma"))
    items = nodes(corpus)
    name = f"{corpus}-{SLUG}"
    collection = client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
    if collection.count() == len(items) and not rebuild:
        return VectorStoreIndex.from_vector_store(ChromaVectorStore(chroma_collection=collection), embed_model=embed_model())
    # Embed first, so a quota error leaves no half-built collection behind
    embed_nodes(items, EmbeddingCache())
    client.delete_collection(name)
    store = ChromaVectorStore(chroma_collection=client.create_collection(name, metadata={"hnsw:space": "cosine"}))
    return VectorStoreIndex(items, storage_context=StorageContext.from_defaults(vector_store=store), embed_model=embed_model())


def numbers(node: NodeWithScore) -> list[int]:
    """The manual questions a node holds: its own, or for a page chunk, every one it overlaps"""
    meta = node.node.metadata
    return [meta["number"]] if "number" in meta else [int(n) for n in meta["numbers"].split()]


class Search:
    """Top k nodes for a query, embedding the query through the cache"""

    def __init__(self, corpus: str = "questions", k: int = 5):
        self.corpus, self.cache = corpus, EmbeddingCache()
        self.retriever = chroma(corpus).as_retriever(similarity_top_k=k)

    def __call__(self, query: str) -> list[NodeWithScore]:
        [vector] = self.cache.embed([query], kind="query")
        return self.retriever.retrieve(QueryBundle(query_str=query, embedding=vector))


if __name__ == "__main__":
    for corpus in CORPORA:
        index = chroma(corpus, rebuild="--rebuild" in sys.argv)
        print(f"{corpus}: {index.vector_store._collection.count()} nodes")
