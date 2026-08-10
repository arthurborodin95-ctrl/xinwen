"""
Модуль для семантической фильтрации новостей с использованием локальной модели sentence-transformers.
Использует модель paraphrase-multilingual-MiniLM-L12-v2, оптимизированную для русского языка.
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import os
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

# --- Конфигурация ---
# Модель для русского языка (оптимальный баланс скорость/качество)
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
# Порог схожести (0.0 - 1.0). Чем выше, тем строже фильтр.
DEFAULT_THRESHOLD = 0.7
# Максимальная длина текста для векторизации (символов)
MAX_TEXT_LENGTH = 500

# --- Инициализация модели (однократная, при первом импорте) ---
_model = None
_topic_vector = None

def _get_model():
    """Ленивая загрузка модели (загружается только при первом вызове)."""
    global _model
    if _model is None:
        try:
            logger.info(f"Загрузка модели {MODEL_NAME}...")
            _model = SentenceTransformer(MODEL_NAME)
            logger.info("Модель успешно загружена.")
        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {e}")
            raise RuntimeError(f"Не удалось загрузить модель: {e}")
    return _model

def embed_text(text: str) -> np.ndarray:
    """
    Преобразует текст в вектор (embedding).
    
    Args:
        text: Текст для векторизации (обрезается до MAX_TEXT_LENGTH символов).
    
    Returns:
        numpy.ndarray: Векторное представление текста.
    """
    model = _get_model()
    # Обрезаем текст для скорости и экономии памяти
    truncated = text[:MAX_TEXT_LENGTH].strip()
    if not truncated:
        truncated = "пустой текст"
    # Векторизуем (model.encode возвращает numpy массив)
    vector = model.encode(truncated, convert_to_numpy=True)
    return vector

def build_topic_embedding(keywords: list) -> np.ndarray:
    """
    Строит эталонный вектор темы на основе списка ключевых слов.
    Используется усреднение векторов всех ключевых слов.
    
    Args:
        keywords: Список ключевых слов (строк).
    
    Returns:
        numpy.ndarray: Усреднённый вектор темы, или None, если список пуст.
    """
    if not keywords:
        logger.warning("Список ключевых слов пуст. Вектор темы не создан.")
        return None
    
    logger.info(f"Построение эталонного вектора по {len(keywords)} ключевым словам...")
    vectors = []
    for kw in keywords:
        try:
            vec = embed_text(kw)
            vectors.append(vec)
        except Exception as e:
            logger.warning(f"Не удалось векторизовать ключевое слово '{kw}': {e}")
            continue
    
    if not vectors:
        logger.error("Не удалось векторизовать ни одно ключевое слово.")
        return None
    
    # Усредняем все векторы
    topic_vector = np.mean(vectors, axis=0)
    logger.info(f"Эталонный вектор создан (размерность: {len(topic_vector)})")
    return topic_vector

def is_semantically_relevant(text: str, topic_vector: np.ndarray, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """
    Проверяет, является ли текст семантически релевантным теме.
    Вычисляет косинусное сходство между вектором текста и эталонным вектором.
    
    Args:
        text: Текст для проверки.
        topic_vector: Эталонный вектор темы (из build_topic_embedding).
        threshold: Порог схожести (0.0 - 1.0). Рекомендуется 0.6-0.8.
    
    Returns:
        bool: True, если текст релевантен, иначе False.
    """
    if topic_vector is None:
        logger.warning("Эталонный вектор не задан. Пропускаем семантическую проверку.")
        return True  # Если нет эталона, считаем все релевантными
    
    if not text or len(text.strip()) < 10:
        return False  # Слишком короткий текст не может быть релевантным
    
    try:
        # Получаем вектор текста
        text_vector = embed_text(text)
        # Вычисляем косинусное сходство
        similarity = cosine_similarity([text_vector], [topic_vector])[0][0]
        # Логируем для отладки (можно закомментировать)
        # logger.debug(f"Сходство: {similarity:.4f} (порог: {threshold})")
        return similarity >= threshold
    except Exception as e:
        logger.error(f"Ошибка при вычислении семантической релевантности: {e}")
        return False  # В случае ошибки считаем нерелевантным

# --- Функция для управления кэшированием (опционально) ---
_cache = {}

def is_semantically_relevant_cached(text: str, topic_vector: np.ndarray, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """
    Кэширующая версия is_semantically_relevant.
    Использует хеш текста для кэширования результата.
    """
    cache_key = hash(text[:200])  # Используем первые 200 символов для кэша
    if cache_key in _cache:
        return _cache[cache_key]
    
    result = is_semantically_relevant(text, topic_vector, threshold)
    _cache[cache_key] = result
    # Ограничиваем размер кэша, чтобы не переполнить память
    if len(_cache) > 1000:
        # Удаляем половину записей
        keys = list(_cache.keys())[:500]
        for k in keys:
            del _cache[k]
    return result
