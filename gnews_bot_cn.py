import requests
import telegram
import time
import asyncio
import os
import re
from dotenv import load_dotenv
from telegram.constants import ParseMode
from telegram.error import BadRequest
from playwright.async_api import async_playwright, Playwright, Browser
from datetime import datetime, timezone, timedelta

# --- Загрузка переменных окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
# Ключевые слова для фильтрации (через запятую)
KEYWORDS_RAW = os.getenv("KEYWORDS", "")
KEYWORDS = ["Логистика", "Китай", "Порт", "экономика"]
# Если переменная не задана или пуста, фильтрация не применяется
if not KEYWORDS:
    print("Ключевые слова не заданы. Будут отправляться все новости.")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GNEWS_API_KEY]):
    print("Ошибка: не все переменные окружения заданы.")
    exit()

# --- Конфигурация ---
MAX_ARTICLES_TO_SEND = 3
SEND_INTERVAL_SECONDS = 20
SENT_ARTICLES_FILE = 'sent_articles.txt'
SENT_TITLES_FILE = 'sent_titles.txt'
CHANNEL_TOPIC_HEADER = "🇷🇺 Новости России"
CONTACT_LINK_TEXT = "Связаться"
CONTACT_LINK_URL = "https://t.me/tl33054"
GROUP_LINK_TEXT = "Чат"
GROUP_LINK_URL = "https://t.me/DONG8NY"

# --- Форматирование времени ---
def format_time(time_str: str) -> str:
    if not time_str:
        return "неизвестно"
    try:
        if time_str.endswith('Z'):
            time_str = time_str[:-1] + '+00:00'
        dt_object = datetime.fromisoformat(time_str)
        msk_tz = timezone(timedelta(hours=3))
        dt_object_msk = dt_object.astimezone(msk_tz)
        return dt_object_msk.strftime('%d.%m.%Y %H:%M')
    except (ValueError, TypeError):
        return time_str.split('T')[0]

# --- Работа с уже отправленными ---
def load_sent_urls():
    if not os.path.exists(SENT_ARTICLES_FILE):
        return set()
    with open(SENT_ARTICLES_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

def save_sent_url(article_url):
    with open(SENT_ARTICLES_FILE, 'a', encoding='utf-8') as f:
        f.write(article_url + '\n')

def load_sent_titles():
    if not os.path.exists(SENT_TITLES_FILE):
        return set()
    with open(SENT_TITLES_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

def save_sent_title(article_title):
    with open(SENT_TITLES_FILE, 'a', encoding='utf-8') as f:
        f.write(article_title + '\n')

# --- Получение новостей с фильтрацией ---
def get_gnews_news():
    print("Запрос новостей из GNews API (Россия)...")
    url = f"https://gnews.io/api/v4/top-headlines?lang=ru&country=ru&max=10&apikey={GNEWS_API_KEY}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"GNews вернул статус {response.status_code}")
            return []
        articles = response.json().get("articles", [])
        if not KEYWORDS:
            print(f"Получено {len(articles)} статей (фильтр отключён).")
            return articles

        filtered = []
        for article in articles:
            title = article.get("title", "")
            description = article.get("description", "")
            content = (title + " " + description).lower()
            if any(kw.lower() in content for kw in KEYWORDS):
                filtered.append(article)
        print(f"Получено {len(articles)} статей, после фильтрации осталось {len(filtered)}.")
        return filtered
    except Exception as e:
        print(f"Ошибка при запросе к GNews: {e}")
        return []

# --- Парсинг полной статьи ---
async def scrape_article_details(page, url: str) -> tuple[str, str]:
    pub_time, summary = "", ""
    try:
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        time_selectors = [
            'meta[property="article:published_time"]',
            'meta[name="publish-date"]',
            'time',
            '.pub_date',
            '.post-time',
            '.time-source .time'
        ]
        for selector in time_selectors:
            element = await page.query_selector(selector)
            if element:
                content = await element.get_attribute('content') or await element.get_attribute('datetime') or await element.inner_text()
                if content:
                    pub_time = content.strip()
                    break
        content_selectors = [
            'article',
            '.article-content',
            '.post-body',
            '.content',
            '#article_content',
            '#Content',
            '.art-text',
            '#main_content',
            'div[class*="content-main"]',
            'div[class*="article-body"]'
        ]
        for selector in content_selectors:
            content_element = await page.query_selector(selector)
            if content_element:
                paragraphs = await content_element.query_selector_all('p')
                summary_parts = [await p.inner_text() for p in paragraphs[:5] if await p.inner_text()]
                if summary_parts:
                    summary = "\n\n".join(summary_parts)
                    if len(paragraphs) > 5:
                        summary += "..."
                    break
        return pub_time, summary
    except Exception as e:
        print(f"Ошибка при парсинге статьи {url}: {e}")
        return pub_time, summary

# --- Отправка одной новости ---
async def send_single_article(bot, article, pub_time: str, summary: str):
    title = article.get('title')
    url = article.get('url')
    image_url = article.get('image')
    source_name = article.get('source', {}).get('name', 'Неизвестный источник')
    if not title or not url:
        return False

    display_time = format_time(pub_time) if pub_time else format_time(article.get('publishedAt'))

    # Генерация хештегов (первые два слова заголовка)
    clean_title = re.sub(r'[^\w\s]', '', title)
    words = clean_title.split()[:2]
    hashtags = " ".join([f"#{word}" for word in words if word]) if words else ""

    summary_text = summary if summary else article.get('description', '')
    if summary_text and title in summary_text:
        summary_text = ""
    if not summary_text:
        summary_text = f"Подробнее: <a href='{url}'>читать полностью</a>."

    caption_parts = [
        f"{CHANNEL_TOPIC_HEADER} {hashtags}\n",
        f"<b>{title}</b>\n",
        summary_text,
        "",
        f"Источник: <a href='{url}'>{source_name}</a>",
        f"Опубликовано: {display_time}",
        f"Связаться: <a href='{CONTACT_LINK_URL}'>{CONTACT_LINK_TEXT}</a>",
        f"💬 Обсудить в чате: <a href='{GROUP_LINK_URL}'>{GROUP_LINK_TEXT}</a>"
    ]
    caption = "\n".join(part for part in caption_parts if part.strip() or part == "")

    if len(caption) > 1024:
        if "Подробнее" not in summary_text:
            oversize = len(caption) - 1024
            summary_text = summary_text[:-(oversize + 5)] + "..."
            caption_parts[2] = summary_text
            caption = "\n".join(part for part in caption_parts if part.strip() or part == "")
        else:
            caption = caption[:1020] + "..."

    try:
        if image_url:
            await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=image_url, caption=caption, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return True
    except Exception as e:
        print(f"Ошибка при отправке: {e}")
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return True
        except Exception as fallback_e:
            print(f"Не удалось отправить даже plain текст: {fallback_e}")
            return False

# --- Основная функция ---
async def main():
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    print("Бот запущен (однократный запуск для serverless).")
    
    browser = None
    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] --- Проверка новых статей ---")
        sent_urls = load_sent_urls()
        sent_titles = load_sent_titles()
        news_articles = get_gnews_news()

        if not news_articles:
            print("Новостей от API не получено или все отфильтрованы.")
        else:
            new_articles = [
                article for article in reversed(news_articles)
                if article.get('url') not in sent_urls and article.get('title') not in sent_titles
            ]
            if not new_articles:
                print("Новых статей (с учётом дублей) нет.")
            else:
                print(f"Найдено {len(new_articles)} новых статей для отправки.")
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True)
                    page = await browser.new_page()

                    sent_count = 0
                    sent_titles_this_run = set()
                    for article in new_articles:
                        if sent_count >= MAX_ARTICLES_TO_SEND:
                            print(f"Достигнут лимит отправки ({MAX_ARTICLES_TO_SEND}) за запуск.")
                            break

                        title = article.get('title')
                        if title in sent_titles_this_run:
                            print(f"Дубликат заголовка в этом запуске: {title}, пропускаем.")
                            save_sent_url(article.get('url'))
                            continue

                        print(f"Обработка: {title}")
                        pub_time, summary = await scrape_article_details(page, article.get('url'))

                        if await send_single_article(bot, article, pub_time, summary):
                            save_sent_url(article.get('url'))
                            save_sent_title(title)
                            sent_titles_this_run.add(title)
                            sent_count += 1
                            print(f"Успешно отправлено ({sent_count}/{MAX_ARTICLES_TO_SEND}).")
                            if sent_count < MAX_ARTICLES_TO_SEND and sent_count < len(new_articles):
                                await asyncio.sleep(SEND_INTERVAL_SECONDS)
                        else:
                            print(f"Не удалось отправить: {title}")

        print("--- Завершено ---")
    except Exception as e:
        print(f"Критическая ошибка в main: {e}")
    finally:
        if browser:
            print("Закрытие браузера...")
            await browser.close()
            print("Браузер закрыт.")

if __name__ == '__main__':
    asyncio.run(main())
