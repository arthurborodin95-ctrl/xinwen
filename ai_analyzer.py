import os
from yandex_ai import call_yandex_gpt

# Проверяем наличие ключей
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
    print("⚠️ YandexGPT не настроен. Анализ новостей будет отключён.")

async def analyze_news(title: str, content: str) -> str:
    """
    Экспертный анализ новости через YandexGPT.
    Возвращает краткий комментарий (2-3 предложения).
    """
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        return "Анализ недоступен: YandexGPT не настроен."

    if not content or len(content.strip()) < 50:
        return "Недостаточно текста для анализа."

    prompt = f"""
Ты — профессиональный аналитик новостей. Проанализируй новость и дай краткую экспертную оценку (2-3 предложения).

Заголовок: {title}
Текст: {content[:1500]}

В ответе укажи:
1. Кому адресована эта новость (аудитория/сектор).
2. Для кого она наиболее важна (бизнес, государство, общество, конкретные отрасли).
3. Какой основной смысл или последствие она несёт.

Ответ должен быть кратким, нейтральным и информативным.
"""
    response = call_yandex_gpt(prompt, max_tokens=200, temperature=0.4)
    return response if response else "Анализ временно недоступен."

async def generate_report(
    total_found: int,
    total_filtered: int,
    total_sent: int,
    sources_checked: list,
    skipped_titles: list,
    errors: list
) -> str:
    """
    Итоговый отчёт о работе бота через YandexGPT.
    """
    if not YANDEX_FOLDER_ID or not YANDEX_API_KEY:
        return "Отчёт недоступен: YandexGPT не настроен."

    sources_sample = sources_checked[:10]
    skipped_sample = skipped_titles[:5]

    prompt = f"""
Ты — технический помощник. Составь краткий отчёт о работе системы за последнюю сессию.

Данные:
- Всего найдено новостей: {total_found}
- После фильтрации: {total_filtered}
- Отправлено в канал: {total_sent}
- Проверенные источники (первые 10): {', '.join(sources_sample)}
- Пропущенные новости (первые 5): {', '.join(skipped_sample)}
- Ошибки: {errors if errors else 'нет'}

Напиши краткий (3-5 предложений) итоговый комментарий:
- Какие источники обработаны.
- Какие новости пропущены и почему (кратко).
- Есть ли системные проблемы.
- Рекомендации по улучшению (если есть).

Ответ должен быть деловым, без лишней воды.
"""
    response = call_yandex_gpt(prompt, max_tokens=300, temperature=0.3)
    return response if response else "Отчёт временно недоступен."
