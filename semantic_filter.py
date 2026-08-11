"""
Модуль для семантической фильтрации новостей с использованием локальной модели sentence-transformers.
Модель: paraphrase-multilingual-MiniLM-L12-v2 (оптимизирована для русского языка).
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

# --- Конфигурация ---
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
DEFAULT_THRESHOLD = 0.7
MAX_TEXT_LENGTH = 500

# --- Глобальные переменные (загружаются один раз) ---
_model = None
_topic_vector = None

def _get_model():
    """Ленивая загрузка модели (загружается только при первом вызове)."""
    global _model
    if _model is None:
        try:
            print(f"🔄 Загрузка модели {MODEL_NAME}...")
            _model = SentenceTransformer(MODEL_NAME)
            print("✅ Модель успешно загружена.")
        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {e}")
            raise
    return _model

def embed_text(text: str) -> np.ndarray:
    """Преобразует текст в вектор (embedding)."""
    model = _get_model()
    truncated = text[:MAX_TEXT_LENGTH].strip()
    if not truncated:
        truncated = "пустой текст"
    vector = model.encode(truncated, convert_to_numpy=True)
    return vector

def build_topic_embedding(keywords: list) -> np.ndarray:
    """
    Строит эталонный вектор темы на основе списка ключевых слов.
    Используется усреднение векторов всех ключевых слов.
    """
    global _topic_vector
    if not keywords:
        print("⚠️ Список ключевых слов пуст. Вектор темы не создан.")
        return None
    
    print(f"📊 Построение эталонного вектора по {len(keywords)} ключевым словам...")
    vectors = []
    for kw in keywords:
        try:
            vec = embed_text(kw)
            vectors.append(vec)
        except Exception as e:
            print(f"  ⚠️ Не удалось векторизовать '{kw}': {e}")
            continue
    
    if not vectors:
        print("❌ Не удалось векторизовать ни одно ключевое слово.")
        return None
    
    _topic_vector = np.mean(vectors, axis=0)
    print(f"✅ Эталонный вектор создан (размерность: {len(_topic_vector)})")
    return _topic_vector

def is_semantically_relevant(text: str, topic_vector: np.ndarray = None, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """
    Проверяет, является ли текст семантически релевантным теме.
    Вычисляет косинусное сходство между вектором текста и эталонным вектором.
    """
    if topic_vector is None:
        global _topic_vector
        topic_vector = _topic_vector
    
    if topic_vector is None:
        print("⚠️ Эталонный вектор не задан. Пропускаем семантическую проверку.")
        return True
    
    if not text or len(text.strip()) < 10:
        return False
    
    try:
        text_vector = embed_text(text)
        similarity = cosine_similarity([text_vector], [topic_vector])[0][0]
        result = similarity >= threshold
        if result:
            print(f"  ✅ Семантическое совпадение: {similarity:.3f} (порог: {threshold})")
        return result
    except Exception as e:
        print(f"  ❌ Ошибка семантической проверки: {e}")
        return False

# --- Кэширование результатов ---
_cache = {}

def is_semantically_relevant_cached(text: str, topic_vector: np.ndarray = None, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Кэширующая версия is_semantically_relevant."""
    if not text or len(text.strip()) < 10:
        return False
    
    cache_key = hash(text[:200])
    if cache_key in _cache:
        return _cache[cache_key]
    
    result = is_semantically_relevant(text, topic_vector, threshold)
    _cache[cache_key] = result
    
    # Ограничиваем размер кэша
    if len(_cache) > 500:
        keys = list(_cache.keys())[:250]
        for k in keys:
            del _cache[k]
    return result
