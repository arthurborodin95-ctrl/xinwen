import requests
import telegram
import time
import asyncio
import os
import re
import sys
from dotenv import load_dotenv
from telegram.constants import ParseMode
from telegram.error import BadRequest
from datetime import datetime, timezone, timedelta
import feedparser

# --- Загрузка переменных окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
KEYWORDS = ["Бартер", "Бартерная торговля", "БРИКС", "Введение в РФ", "Ввезли в Россию", "Ввоз в Россию", "Ввоз оборудования", "Виза в РФ", "Внешняя торговля", "ВЭД", "ЕАЭС", "ЕЭК", "Завезли в Россию", "Запущено производство", "Из Китая", "Из-за рубежа", "Импорт", "Импорт в Китай", "Импорт из Китая", "Импорт из Южной Кореи", "Импорт из Японии", "Импортер", "Импортируемый", "Импортный", "Импортозамещение", "Иностранный", "Иностранный бизнес", "Контрафакт", "Логистика в РФ", "Локализация производства", "Маркировка в РФ", "Минпромторг", "Минэкономразвития", "МИД РФ", "Налогообложение импорта", "Обнуление пошлин", "Ограничение на въезд/выезд", "Открытие границ", "Параллельный импорт", "Поставка в Россию", "Пошлины на импорт", "Платежи в Китай", "Привлечение иностранных инвестиций", "Россельхознадзор", "Санкции", "Ставки перевозок", "Станкостроение", "Таможня", "Транзит через Россию", "Трансграничные платежи", "Трансграничный перевод", "Туризм", "ФТС РФ", "Цифровая валюта", "Цифровой финансовый актив (ЦФА)", "Экспорт в Россию", "Экспорт из Южной Кореи", "Экспорт из Японии", "Экспорт из Китая"]
if not KEYWORDS:
    print("Ключевые слова не заданы. Будут отправляться все новости.")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    print("Ошибка: не все переменные окружения заданы (токен и ID канала обязательны).")
    sys.exit(1)

# --- Конфигурация ---
MAX_ARTICLES_TO_SEND = 8
SEND_INTERVAL_SECONDS = 20
SENT_ARTICLES_FILE = 'sent_articles.txt'
SENT_TITLES_FILE = 'sent_titles.txt'
CHANNEL_TOPIC_HEADER = "🇷🇺 Новости России"
CONTACT_LINK_TEXT = "Связаться"
CONTACT_LINK_URL = "https://t.me/tl33054"
GROUP_LINK_TEXT = "Чат"
GROUP_LINK_URL = "https://t.me/DONG8NY"

# --- Список RSS-лент ---
RSS_FEEDS = [
    "https://ria.ru/export/rss2/index.xml",
    "https://tass.ru/rss/v2.xml",
    "https://www.interfax.ru/rss.asp",
    "https://www.finmarket.ru/export/rss.asp",
    "https://www.kommersant.ru/RSS/news.xml",
    "https://www.vedomosti.ru/rss",
    "https://1prime.ru/export/rss.xml",
    "https://www.forbes.ru/rss/all",
    "https://iz.ru/xml/rss/all.xml",
    "https://www.tks.ru/law.rss",
    "https://www.tks.ru/nearby.rss",
    "https://trans.ru/rss/news",
    "https://www.infranews.ru/feed/",
    "https://www.tourdom.ru/rss/",
    "https://www.autostat.ru/export/rss/",
    "https://morvesti.ru/rss/",
    "https://portnews.ru/rss/",
    "https://seanews.ru/feed/",
    "https://primpress.ru/rss/",
    "https://www.ixbt.com/export/news.rss",
    "https://www.cnews.ru/news/rss",
    "https://www.comnews.ru/rss",
    "http://www.cbr.ru/rss/RssNews",
    "http://www.cbr.ru/rss/RssPress",
    "https://biang.ru/rss/",
    "http://russian.news.cn/rss/news.xml",
    "https://www.eastrussia.ru/feed/",
    "https://bigasia.ru/feed/",
    "http://russian.china.org.cn/rss/feed.xml",
    "http://russian.people.com.cn/rss/feed.xml",
    "https://rsshub.app/cnbc/rss/",
    "https://www.scmp.com/rss/",
    "https://tvbrics.com/feed/"
]
MAX_ARTICLES_PER_FEED = 5

# --- Форматирование времени (безопасное) ---
def format_time(time_str: str) -> str:
    if not time_str:
        return "неизвестно"
    try:
        # Пытаемся распарсить ISO-формат
        if time_str.endswith('Z'):
            time_str = time_str[:-1] + '+00:00'
        dt_object = datetime.fromisoformat(time_str)
        msk_tz = timezone(timedelta(hours=3))
        dt_object_msk = dt_object.astimezone(msk_tz)
        return dt_object_msk.strftime('%d.%m.%Y %H:%M')
    except (ValueError, TypeError):
        # Если не получается, возвращаем как есть
        return time_str

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

# --- Получение новостей из RSS ---
def get_news_from_rss():
    all_articles = []
    seen_urls = set()

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            print(f"Парсинг RSS: {feed_url}, найдено {len(feed.entries)} записей.")
            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                if not entry.get('link') or not entry.get('title'):
                    continue
                if entry.link in seen_urls:
                    continue
                seen_urls.add(entry.link)

                # Дата публикации
                pub_date_iso = None
                if entry.get('published_parsed'):
                    dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    pub_date_iso = dt.isoformat()
                elif entry.get('published'):
                    pub_date_iso = entry.published
                else:
                    pub_date_iso = datetime.now(timezone.utc).isoformat()

                description = entry.get('summary', '') or entry.get('description', '')

                # Изображение
                image_url = None
                if 'media_content' in entry and entry.media_content:
                    image_url = entry.media_content[0].get('url')
                elif 'links' in entry:
                    for link in entry.links:
                        if link.get('type', '').startswith('image'):
                            image_url = link.get('href')
                            break

                source_name = feed.feed.get('title', 'Неизвестный источник')

                article = {
                    'title': entry.title,
                    'url': entry.link,
                    'description': description,
                    'publishedAt': pub_date_iso,
                    'source': {'name': source_name},
                    'image': image_url,
                }
                all_articles.append(article)
        except Exception as e:
            print(f"Ошибка при парсинге RSS {feed_url}: {e}")

    # Сортировка по дате (новые сверху)
    def get_date(article):
        try:
            return datetime.fromisoformat(article.get('publishedAt', ''))
        except:
            return datetime.min

    all_articles.sort(key=get_date, reverse=True)
    print(f"Всего собрано {len(all_articles)} статей из RSS.")
    return all_articles

# --- Фильтрация по ключевым словам ---
def filter_articles_by_keywords(articles):
    if not KEYWORDS:
        return articles
    filtered = []
    for article in articles:
        title = article.get("title", "")
        description = article.get("description", "")
        content = (title + " " + description).lower()
        if any(kw.lower() in content for kw in KEYWORDS):
            filtered.append(article)
    print(f"После фильтрации по ключевым словам осталось {len(filtered)} из {len(articles)} статей.")
    return filtered

# --- Парсинг полной статьи (с защитой от падений) ---
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

    # Хештеги из первых двух слов
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

# --- Основная функция с защитой от падений playwright ---
async def main():
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    print("Бот запущен (однократный запуск для serverless).")
    
    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] --- Проверка новых статей ---")
        sent_urls = load_sent_urls()
        sent_titles = load_sent_titles()

        all_news = get_news_from_rss()
        filtered_news = filter_articles_by_keywords(all_news)

        if not filtered_news:
            print("Нет новостей после фильтрации.")
            return

        new_articles = [
            article for article in filtered_news
            if article.get('url') not in sent_urls and article.get('title') not in sent_titles
        ]
        if not new_articles:
            print("Новых статей (с учётом дублей) нет.")
            return

        print(f"Найдено {len(new_articles)} новых статей для отправки.")

        # Попытка использовать Playwright для парсинга полного текста
        browser = None
        playwright_available = True
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                # ... дальше обработка
        except Exception as e:
            print(f"Playwright недоступен или не удалось запустить браузер: {e}. Будем отправлять новости без парсинга.")
            playwright_available = False

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

            pub_time = ""
            summary = ""
            if playwright_available and browser:
                try:
                    pub_time, summary = await scrape_article_details(page, article.get('url'))
                except Exception as e:
                    print(f"Ошибка при парсинге страницы: {e}")
                    # оставляем пустые pub_time и summary

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

        if browser:
            await browser.close()
        print("--- Завершено ---")
    except Exception as e:
        print(f"Критическая ошибка в main: {e}")
        # Не прерываем выполнение с ошибкой, просто логируем

if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)  # Завершаем успешно, даже если были ошибки внутри (они уже залогированы)
if __name__ == '__main__':
    asyncio.run(main())
