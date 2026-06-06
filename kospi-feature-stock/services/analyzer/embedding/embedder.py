import logging
import numpy as np
from typing import Union

logger = logging.getLogger(__name__)

MODEL_NAME = "jhgan/ko-sroberta-multitask"
DIM = 384


class LocalEmbedder:
    """
    로컬 Sentence-BERT (한국어 특화).
    sentence-transformers 라이브러리 사용.
    외부 API 없이 완전 로컬 동작.
    """

    def __init__(self, model_name: str = MODEL_NAME, cache_dir: str = "/models"):
        self._model = None
        self._model_name = model_name
        self._cache_dir  = cache_dir
        self._dim = DIM

    def _load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                self._model_name,
                cache_folder=f"{self._cache_dir}/sentence-bert",
            )
            self._dim = self._model.get_sentence_embedding_dimension()
            logger.info(f"Loaded: {self._model_name} dim={self._dim}")
        except Exception as e:
            logger.warning(f"Model load failed: {e} — using zero vectors")

    def encode(
        self,
        texts: Union[str, list[str]],
        batch_size: int = 32,
    ) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]

        self._load()
        if self._model is None:
            return np.zeros((len(texts), self._dim), dtype=np.float32)

        try:
            return self._model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).astype(np.float32)
        except Exception as e:
            logger.error(f"Encode error: {e}")
            return np.zeros((len(texts), self._dim), dtype=np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def encode_disclosure(self, title: str, content: str = "") -> np.ndarray:
        combined = f"{title} {content[:500]}"
        return self.encode_one(combined)
