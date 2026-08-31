import os
import json
import requests
from datetime import datetime

FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
API_KEY = os.getenv("YANDEX_API_KEY")
BASE_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

def call_yandex_gpt(prompt: str, max_tokens: int = 500, temperature: float = 0.5) -> str:
    if not FOLDER_ID or not API_KEY:
        print("⚠️ YandexGPT не настроен.")
        return None
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
        "messages": [{"role": "user", "text": prompt}],
    }
    try:
        response = requests.post(BASE_URL, headers=headers, json=body, timeout=30)
        response.raise_for_status()
        result = response.json()
        if "result" in result and "alternatives" in result["result"]:
            return result["result"]["alternatives"][0]["message"]["text"]
        return None
    except Exception as e:
        print(f"Ошибка YandexGPT: {e}")
        return None

def summarize_article(title: str, content: str) -> str:
    if not content:
        return None
    if len(content) > 4000:
        content = content[:4000] + "..."
    prompt = f"""
Заголовок: {title}
Текст статьи:
{content}
Сделай краткое резюме новости (3-5 предложений). Выдели главное, факты, субъект новости.
Резюме:
"""
    return call_yandex_gpt(prompt, max_tokens=400, temperature=0.4)

def extract_tags(title: str, content: str) -> list:
    if not content:
        return []
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
        return [tag.strip() for tag in tags_text.split(",") if tag.strip()][:5]
    return []

def analyze_sentiment(title: str, content: str) -> dict:
    if not content:
        return {"sentiment": "neutral", "confidence": 0.5}
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
            start = result.find("{")
            end = result.rfind("}") + 1
            if start != -1 and end != -1:
                return json.loads(result[start:end])
        except:
            pass
    return {"sentiment": "neutral", "confidence": 0.5}

# ============================================================
# ФУНКЦИЯ ПОЛУЧЕНИЯ ЭМБЕДДИНГА (исправленная модель)
# ============================================================

def get_embedding(text: str) -> list:
    """
    Отправляет текст в YandexGPT Embeddings и возвращает вектор.
    """
    if not FOLDER_ID or not API_KEY:
        print("⚠️ YandexGPT не настроен (FOLDER_ID или API_KEY отсутствуют).")
        return None

    # Используем модель text-search-query/latest (как в рабочем примере)
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"
    headers = {
        "Authorization": f"Api-Key {API_KEY}",
        "Content-Type": "application/json",
    }
    model_uri = f"emb://{FOLDER_ID}/text-search-query/latest"
    payload = {
        "modelUri": model_uri,
        "text": text[:500],
    }

    # Отладочный вывод (можно закомментировать после проверки)
    print(f"🔍 Отправка запроса на эмбеддинг:")
    print(f"   URL: {url}")
    print(f"   modelUri: {model_uri}")
    print(f"   text: {text[:50]}...")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        embedding = result.get("embedding")
        if embedding:
            print(f"   ✅ Эмбеддинг получен, размерность: {len(embedding)}")
            return embedding
        else:
            print("⚠️ В ответе не найден 'embedding'")
            return None
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP ошибка при получении эмбеддинга: {e}")
        if response.status_code == 400:
            print("   Причина 400: неверный modelUri или текст. Проверьте FOLDER_ID и модель.")
            print(f"   Отправленный modelUri: {model_uri}")
        elif response.status_code == 401:
            print("   Неверный API-ключ или Folder ID.")
        elif response.status_code == 403:
            print("   Недостаточно прав для доступа к эмбеддингам.")
        # Покажем тело ответа для диагностики
        try:
            print(f"   Тело ответа: {response.text}")
        except:
            pass
        return None
    except Exception as e:
        print(f"❌ Ошибка получения эмбеддинга: {e}")
        return None