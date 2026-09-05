#!/usr/bin/env python3
"""
Скрипт для адаптивной настройки фильтров бота на основе обратной связи пользователей.
Запускается по cron (например, раз в сутки).
"""
import os
import sys
import json
import logging
from collections import Counter
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

# Импорты из проекта
from db import (
    init_db,
    init_config_table,
    get_config,
    set_config,
    get_keywords,
    set_keywords,
    get_excluded_keywords,
    set_excluded_keywords,
    get_semantic_threshold,
    set_semantic_threshold,
    get_recent_feedback_stats,
)
from news_fetcher import fetch_gnews
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --- Вспомогательные функции ---

def normalize_word(word: str) -> str:
    """Приводит слово к нижнему регистру, убирает знаки препинания."""
    word = re.sub(r'[^\w]', '', word).lower()
    return word

def get_word_frequencies(texts: list, min_len=3) -> Counter:
    """
    Из списка текстов извлекает частоту слов.
    Убирает стоп-слова (можно расширить список).
    """
    stopwords = {'и', 'в', 'на', 'с', 'по', 'для', 'из', 'что', 'как', 'это', 'не', 'или', 'их', 'все', 'так', 'уже'}
    counter = Counter()
    for text in texts:
        words = re.findall(r'\b\w+\b', text.lower())
        for word in words:
            if len(word) >= min_len and word not in stopwords:
                counter[word] += 1
    return counter

# --- Основная логика адаптации ---

def adjust_filters():
    logger.info("Начинаем адаптацию фильтров на основе отзывов...")

    # 1. Получаем статистику отзывов
    avg_rating, count = get_recent_feedback_stats(days=7)
    logger.info(f"За последние 7 дней получено {count} оценок, средний рейтинг: {avg_rating:.2f}")

    # Если отзывов мало – не меняем настройки
    if count < 10:
        logger.info("Недостаточно отзывов для корректировки (нужно >= 10). Пропускаем.")
        return

    # 2. Корректировка порога семантической схожести
    current_threshold = get_semantic_threshold()
    new_threshold = current_threshold

    # Если пользователи в среднем ставят низкие оценки, значит фильтр слишком строгий → понижаем порог (пропускаем больше)
    # Если высокие – значит качество хорошее, можно повысить порог (оставляем только самое релевантное)
    if avg_rating < 3.0:
        new_threshold = max(0.4, current_threshold - 0.05)
        logger.info(f"Средний рейтинг низкий ({avg_rating:.2f}), понижаем порог до {new_threshold:.2f}")
    elif avg_rating > 4.0:
        new_threshold = min(0.9, current_threshold + 0.05)
        logger.info(f"Средний рейтинг высокий ({avg_rating:.2f}), повышаем порог до {new_threshold:.2f}")
    else:
        logger.info(f"Средний рейтинг в норме, порог не меняем ({current_threshold:.2f})")

    if new_threshold != current_threshold:
        set_semantic_threshold(new_threshold)

    # 3. Анализ ключевых слов и исключений
    # Получаем тексты новостей, которые пользователи оценили как полезные (rating > 0) и бесполезные (rating < 0)
    # Для этого нужно получить данные из БД (можно добавить функцию get_feedback_texts() в db.py)
    # Для примера используем заглушку: если у нас нет реальных данных, мы не будем менять слова.
    # В реальном проекте нужно добавить в db.py функцию, которая возвращает тексты с рейтингом.
    # Пока просто логируем, что можно было бы сделать.
    logger.info("Анализ ключевых слов и исключений пока не реализован, требуется расширение db.py.")
    # В будущем можно реализовать:
    # good_texts, bad_texts = get_feedback_texts()
    # good_words = get_word_frequencies(good_texts)
    # bad_words = get_word_frequencies(bad_texts)
    # и т.д.

    logger.info("Адаптация завершена.")

if __name__ == '__main__':
    # Инициализация БД и таблицы конфигурации
    init_db()
    init_config_table()
    adjust_filters()
