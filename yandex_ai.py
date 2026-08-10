import os
import json
import requests
from datetime import datetime

FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
API_KEY = os.getenv("YANDEX_API_KEY")
BASE_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

def call_yandex_gpt(prompt: str, max_tokens: int = 500, temperature: float = 0.5) -> str:
    """
    Отправляет запрос к YandexGPT Lite и возвращает ответ.
    Документация: https://cloud.yandex.ru/docs/yandexgpt/api-ref/v1/TextGeneration/completion
    """
    headers = {
        "Authorization": f"Api-Key {API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": temperature,
            "maxTokens": max_tokens,
        },
        "messages": [
            {
                "role": "user",
                "text": prompt,
            }
        ],
    }

    try:
        response = requests.post(BASE_URL, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        result = response.json()
        # Извлекаем текст ответа
        if "result" in result and "alternatives" in result["result"]:
            return result["result"]["alternatives"][0]["message"]["text"]
        else:
            return None
    except Exception as e:
        print(f"Ошибка при запросе к YandexGPT: {e}")
        return None

def summarize_article(title: str, content: str) -> str:
    """
    Суммаризирует статью. Если контент слишком длинный, обрезает до 4000 символов.
    """
    # Обрезаем до 4000 символов (YandexGPT Lite принимает до 6000 токенов)
    if len(content) > 4000:
        content = content[:4000] + "..."
    
    prompt = f"""
Заголовок: {title}

Текст статьи:
{content}

Сделай краткое резюме новости (3-5 предложений). Выдели главное, факты, субъект новости. Пиши нейтрально и по делу.

Резюме:
"""
    summary = call_yandex_gpt(prompt, max_tokens=400, temperature=0.4)
    if summary:
        # Убираем лишние пробелы
        return summary.strip()
    return None

def extract_tags(title: str, content: str) -> list:
    """
    Извлекает 3-5 ключевых тегов для новости.
    """
    if len(content) > 2000:
        content = content[:2000] + "..."
    
    prompt = f"""
Заголовок: {title}

Текст статьи:
{content}

Извлеки 3-5 ключевых тегов (слова или короткие фразы), которые лучше всего описывают тему новости.
Ответь только списком тегов через запятую. Не добавляй пояснений.

Теги:
"""
    tags_text = call_yandex_gpt(prompt, max_tokens=100, temperature=0.3)
    if tags_text:
        # Разбиваем по запятой и чистим
        tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()]
        return tags[:5]  # не больше 5
    return []

def analyze_sentiment(title: str, content: str) -> dict:
    """
    Определяет тональность новости: positive, negative, neutral + достоверность.
    """
    if len(content) > 1500:
        content = content[:1500] + "..."
    
    prompt = f"""
Заголовок: {title}

Текст статьи:
{content}

Определи тональность новости (positive, negative, neutral) и укажи достоверность (от 0 до 1).
Ответь строго в формате JSON: {{"sentiment": "positive/negative/neutral", "confidence": 0.0-1.0}}

Ответ JSON:
"""
    result = call_yandex_gpt(prompt, max_tokens=100, temperature=0.2)
    if result:
        try:
            # Ищем JSON в ответе
            start = result.find("{")
            end = result.rfind("}") + 1
            if start != -1 and end != -1:
                return json.loads(result[start:end])
        except:
            pass
    return {"sentiment": "neutral", "confidence": 0.5}
    def get_embedding(text: str) -> list:
    """
    Получает векторное представление текста через YandexGPT Embeddings.
    Документация: https://cloud.yandex.ru/docs/yandexgpt/api-ref/Embedding
    """
    url = "https://llm.api.cloud.yandex.net/embeddings"
    headers = {
        "Authorization": f"Api-Key {API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "modelUri": f"emb://{FOLDER_ID}/text-embedding-004",  # или другая модель
        "text": text[:500],  # ограничиваем длину для экономии
    }
    try:
        response = requests.post(url, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("embedding", [])
    except Exception as e:
        print(f"Ошибка получения эмбеддинга: {e}")
        return None
