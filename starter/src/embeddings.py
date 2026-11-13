"""Local Sentence Transformers embedder. A real model or an error: there is no mock fallback."""
from typing import Protocol

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"
REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"  # Hugging Face commit, pinned so reruns embed identically
# The model card recommends this instruction on short queries for passage retrieval; documents get none.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Unit-length vectors, so cosine distance in the store ranks them correctly."""

    def __init__(self, model_name: str = MODEL_NAME, revision: str = REVISION) -> None:
        self.model_name, self.revision = model_name, revision
        # Raises if the model cannot be downloaded or loaded.
        self._model = SentenceTransformer(model_name, revision=revision)
        self.dimensions = self._model.get_embedding_dimension()
        self.max_tokens = self._model.max_seq_length
        self.device = str(self._model.device)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, batch_size=64, normalize_embeddings=True).tolist()

    def embed_query(self, question: str) -> list[float]:
        return self._model.encode(QUERY_PREFIX + question, normalize_embeddings=True).tolist()

    def token_counts(self, texts: list[str]) -> list[int]:
        """Tokens per text including special tokens; anything above max_tokens is truncated by the model."""
        return [len(ids) for ids in self._model.tokenizer(texts)["input_ids"]]
