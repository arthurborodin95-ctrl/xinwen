import os
from openrouter import OpenRouter

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    print("⚠️ OPENROUTER_API_KEY не задан. Анализ новостей будет отключён.")

client = OpenRouter(api_key=API_KEY) if API_KEY else None

# Модель для анализа новостей (бесплатная)
ANALYSIS_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
REPORT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

async def analyze_news(title: str, content: str) -> str:
    """
    Экспертный анализ новости через OpenRouter.
    Возвращает краткий комментарий (2-3 предложения).
    """
    if client is None:
        return "Анализ недоступен (ключ не задан)."
    
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
    try:
        response = client.chat.send(
            model=ANALYSIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Ошибка при анализе новости: {e}")
        return f"Анализ временно недоступен ({str(e)[:50]})"

async def generate_report(
    total_found: int,
    total_filtered: int,
    total_sent: int,
    sources_checked: list,
    skipped_titles: list,
    errors: list
) -> str:
    """
    Итоговый отчёт о работе бота через OpenRouter.
    """
    if client is None:
        return "Отчёт недоступен (ключ не задан)."

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
    try:
        response = client.chat.send(
            model=REPORT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Ошибка при генерации отчёта: {e}")
        return f"Отчёт временно недоступен ({str(e)[:50]})"
