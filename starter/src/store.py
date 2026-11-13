"""PostgreSQL + pgvector store: one row per (strategy, chunk), cosine distance, exact scan (no ANN index)."""
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .models import Chunk

METADATA = ("document_id", "source", "page", "char_start", "char_end", "publisher", "year", "section")
FILTERABLE = ("document_id", "publisher", "year", "section")  # only these column names ever reach SQL text
COLUMNS = ("strategy", "chunk_id", *METADATA, "text", "embedding")


def _vector(values: list[float]) -> str:
    """pgvector text literal, so no extra client library is needed."""
    return "[" + ",".join(map(repr, values)) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError(f"embedding dimensions must be positive, got {dimensions}")
        self.database_url, self.dimensions = database_url, dimensions

    def _connect(self) -> psycopg.Connection:
        # ponytail: one connection per call (commit on exit, rollback on error); pool if latency matters
        return psycopg.connect(self.database_url, connect_timeout=5, row_factory=dict_row)

    def create_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"""CREATE TABLE IF NOT EXISTS chunks (
                strategy text NOT NULL, chunk_id text NOT NULL,
                document_id text NOT NULL, source text NOT NULL, page int NOT NULL,
                char_start int NOT NULL, char_end int NOT NULL,
                publisher text NOT NULL, year int NOT NULL, section text NOT NULL,
                text text NOT NULL, embedding vector({self.dimensions:d}) NOT NULL,
                PRIMARY KEY (strategy, chunk_id))""")
            stored = conn.execute("SELECT atttypmod FROM pg_attribute WHERE attrelid = 'chunks'::regclass "
                                  "AND attname = 'embedding'").fetchone()["atttypmod"]
        if stored != self.dimensions:
            raise RuntimeError(f"table chunks stores vector({stored}) but the model has {self.dimensions} "
                               "dimensions; drop the table before switching embedding models")

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Make the stored strategy equal to `chunks`: insert new IDs, overwrite existing, delete obsolete."""
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if bad := {len(v) for v in vectors} - {self.dimensions}:
            raise ValueError(f"expected {self.dimensions}-dimensional vectors, got {sorted(bad)}")
        ids = [c.chunk_id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk IDs")
        rows = [(strategy, c.chunk_id, c.document_id, c.source, c.page, *(c.metadata[k] for k in METADATA[3:]),
                 c.text, _vector(v)) for c, v in zip(chunks, vectors)]
        updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in COLUMNS[2:])
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO chunks ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
                f"ON CONFLICT (strategy, chunk_id) DO UPDATE SET {updates}", rows)
            cur.execute("DELETE FROM chunks WHERE strategy = %s AND chunk_id <> ALL(%s)", (strategy, ids))

    def count(self, strategy: str) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT count(*) AS n FROM chunks WHERE strategy = %s", (strategy,)).fetchone()["n"]

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Top-k by cosine similarity among rows matching every filter; ties broken by chunk ID."""
        filters = filters or {}
        if unknown := set(filters) - set(FILTERABLE):
            raise ValueError(f"cannot filter on {sorted(unknown)}; allowed: {FILTERABLE}")
        where = "".join(f" AND {column} = %s" for column in filters)
        vector = _vector(query_vector)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT chunk_id, text, 1 - (embedding <=> %s::vector) AS score, {', '.join(METADATA)} "
                f"FROM chunks WHERE strategy = %s{where} ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s",
                (vector, strategy, *filters.values(), vector, top_k)).fetchall()
        return [{"chunk_id": r["chunk_id"], "text": r["text"], "score": round(r["score"], 4),
                 "metadata": {k: r[k] for k in METADATA}} for r in rows]


def demo() -> None:
    """Self-check against the real database and the real model: python -m src.store"""
    import os

    from dotenv import load_dotenv

    from .embeddings import MyEmbedder
    from .ingestion import DATA_DIR

    load_dotenv(DATA_DIR.parent / ".env")
    embedder = MyEmbedder()
    store = PgVectorStore(os.environ["DATABASE_URL"], embedder.dimensions)
    store.create_schema()
    texts = {1: ("Adults need seven to nine hours of sleep each night.", "X"),
             2: ("Limit sodium to less than 2,300 milligrams per day.", "X"),
             3: ("Sleep at least seven hours every night.", "Y")}
    chunks = [Chunk(f"t:{i}", "t", "t.pdf", i, text, {"char_start": 0, "char_end": len(text), "publisher": pub,
                                                      "year": 2020, "section": "s"}) for i, (text, pub) in texts.items()]
    vectors = embedder.embed_documents([c.text for c in chunks])
    name = "_selfcheck"
    try:
        store.upsert(name, chunks, vectors)
        store.upsert(name, chunks, vectors)
        assert store.count(name) == 3, "re-ingesting the same chunks must not duplicate rows"
        query = embedder.embed_query("How many hours should adults sleep?")
        top = store.search(name, query, top_k=2)
        assert {h["chunk_id"] for h in top} == {"t:1", "t:3"} and 1 >= top[0]["score"] >= top[1]["score"], top
        assert top[0]["metadata"]["page"] in (1, 3) and top[0]["metadata"]["source"] == "t.pdf"
        assert [h["chunk_id"] for h in store.search(name, query, filters={"publisher": "Y"})] == ["t:3"]
        assert store.search(name, query, filters={"publisher": "'; DROP TABLE chunks; --"}) == []
        store.upsert(name, chunks[:1], vectors[:1])
        assert store.count(name) == 1, "chunks missing from the new version must be deleted"
        for bad in (lambda: store.search(name, query, filters={"text": "x"}),
                    lambda: store.upsert(name, chunks, vectors[:2]),
                    lambda: store.upsert(name, chunks[:1], [[0.0]])):
            try:
                bad()
            except ValueError:
                continue
            raise AssertionError("invalid input was accepted")
    finally:
        store.upsert(name, [], [])
    assert store.count(name) == 0
    print(f"store OK ({embedder.model_name}, {embedder.dimensions} dims, max {embedder.max_tokens} tokens, "
          f"{embedder.device}, revision {embedder.revision})")


if __name__ == "__main__":
    demo()
