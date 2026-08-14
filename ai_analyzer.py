import os
from yandex_ai import call_yandex_gpt

# Проверяем наличие ключей (без этого отчёт не сгенерируется)
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
    print("⚠️ YandexGPT не настроен. Итоговый отчёт будет отключён.")

async def generate_report(
    total_found: int,
    total_filtered: int,
    total_sent: int,
    semantic_stats: dict,
    sources_checked: list = None,
    skipped_titles: list = None,
    errors: list = None
) -> str:
    """
    Итоговый отчёт о работе системы через YandexGPT.
    Вся аналитика собирается на основе переданных данных.
    """
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        return "Отчёт недоступен: YandexGPT не настроен."

    # Подготовка данных для промпта
    threshold = semantic_stats.get('threshold', 0.7)
    passed = semantic_stats.get('passed', 0)
    failed = semantic_stats.get('failed', 0)
    avg_sim = semantic_stats.get('avg_similarity', 0)

    sources_sample = sources_checked[:10] if sources_checked else []
    skipped_sample = skipped_titles[:5] if skipped_titles else []

    prompt = f"""
Ты — технический помощник. Составь краткий отчёт о работе системы за последнюю сессию.

Данные:
- Всего найдено новостей: {total_found}
- После фильтрации по ключевым словам: {total_filtered}
- После семантической фильтрации (порог {threshold}): принято {passed}, отклонено {failed}
- Средняя схожесть: {avg_sim:.3f}
- Отправлено в канал (новых): {total_sent}
- Проверенные источники (первые 10): {', '.join(sources_sample) if sources_sample else 'не указаны'}
- Пропущенные новости (первые 5): {', '.join(skipped_sample) if skipped_sample else 'нет'}
- Ошибки: {errors if errors else 'нет'}

Напиши краткий (3-5 предложений) итоговый комментарий:
- Какие фильтры сработали и насколько эффективно.
- Какие новости были отклонены и почему (кратко).
- Есть ли системные проблемы.
- Рекомендации по улучшению фильтрации.

Ответ должен быть деловым, без лишней воды.
"""
    response = call_yandex_gpt(prompt, max_tokens=500, temperature=0.3)
    return response if response else "Отчёт временно недоступен (ошибка YandexGPT)."
