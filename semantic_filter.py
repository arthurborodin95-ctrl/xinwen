import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Загружаем модель (однократно, при импорте)
model = SentenceTransformer('all-MiniLM-L6-v2')

def embed_text(text: str) -> np.ndarray:
    """Возвращает вектор для текста (обрезает до 500 символов для скорости)."""
    return model.encode(text[:500])

def build_topic_embedding(keywords: list) -> np.ndarray:
    """Строит усреднённый вектор по списку ключевых слов."""
    if not keywords:
        return None
    vectors = [embed_text(kw) for kw in keywords]
    return np.mean(vectors, axis=0)

def is_semantically_relevant(text: str, topic_vector: np.ndarray, threshold: float = 0.7) -> bool:
    if topic_vector is None:
        return True  # если нет эталона, пропускаем все
    vec = embed_text(text)
    sim = cosine_similarity([vec], [topic_vector])[0][0]
    return sim >= threshold
