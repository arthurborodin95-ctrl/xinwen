import os
import sys
import json
import logging
import re
from collections import Counter
from dotenv import load_dotenv
load_dotenv()

from db import (
    init_db,
    get_keywords,
    set_keywords,
    get_excluded_keywords,
    set_excluded_keywords,
    get_semantic_threshold,
    set_semantic_threshold,
    get_recent_feedback_stats,
    get_feedback_texts
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def adjust_filters():
    init_db()
    logger.info("Начинаем адаптацию фильтров...")
    avg_rating, count = get_recent_feedback_stats(days=7)
    logger.info(f"Оценок за 7 дней: {count}, средняя: {avg_rating:.2f}")
    if count < 10:
        logger.info("Недостаточно отзывов. Пропускаем.")
        return

    # Корректировка порога
    current = get_semantic_threshold()
    if avg_rating < 3.0:
        new = max(0.4, current - 0.05)
        set_semantic_threshold(new)
        logger.info(f"Порог понижен до {new:.2f}")
    elif avg_rating > 4.0:
        new = min(0.9, current + 0.05)
        set_semantic_threshold(new)
        logger.info(f"Порог повышен до {new:.2f}")

    # Анализ слов
    good, bad = get_feedback_texts(days=7)
    if good or bad:
        good_words = Counter()
        for text in good:
            for word in re.findall(r'\b\w{3,}\b', text.lower()):
                good_words[word] += 1
        bad_words = Counter()
        for text in bad:
            for word in re.findall(r'\b\w{3,}\b', text.lower()):
                bad_words[word] += 1

        # Добавляем часто встречающиеся в полезных новостях слова
        current_keywords = set(get_keywords())
        new_keywords = set(current_keywords)
        for word, count in good_words.most_common(5):
            if count >= 3 and word not in current_keywords:
                new_keywords.add(word)
        set_keywords(list(new_keywords))
        logger.info(f"Ключевые слова обновлены: {len(new_keywords)} слов")

        # Добавляем в исключения слова из негативных отзывов
        current_excluded = set(get_excluded_keywords())
        new_excluded = set(current_excluded)
        for word, count in bad_words.most_common(3):
            if count >= 2 and word not in current_excluded:
                new_excluded.add(word)
        set_excluded_keywords(list(new_excluded))
        logger.info(f"Список исключений обновлён: {len(new_excluded)} слов")

if __name__ == '__main__':
    adjust_filters()
