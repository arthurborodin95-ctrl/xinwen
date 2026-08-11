import telegram
import time
import asyncio
import os
import re
import sys
from dotenv import load_dotenv
from telegram.constants import ParseMode
from datetime import datetime, timezone, timedelta
import feedparser

# --- Загрузка переменных окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

KEYWORDS = [
    "Бартер", "Бартерная торговля", "БРИКС", "Введение в РФ", "Китай", "Китайская экономика",
    "Ввезли в Россию", "Ввоз в Россию", "Ввоз оборудования", "Виза в РФ", "Внешняя торговля",
    "ВЭД", "ЕАЭС", "ЕЭК", "Завезли в Россию", "Запущено производство", "Из Китая", "Из-за рубежа",
    "Импорт", "Импорт в Китай", "Импорт из Китая", "Импорт из Южной Кореи", "Импорт из Японии",
    "Импортер", "Импортируемый", "Импортный", "Импортозамещение", "Иностранный", "Иностранный бизнес",
    "Контрафакт", "Логистика в РФ", "Локализация производства", "Маркировка в РФ", "Минпромторг",
    "Минэкономразвития", "МИД РФ", "Налогообложение импорта", "Обнуление пошлин",
    "Ограничение на въезд/выезд", "Открытие границ", "Параллельный импорт", "Поставка в Россию",
    "Пошлины на импорт", "Платежи в Китай", "Привлечение иностранных инвестиций", "Россельхознадзор",
    "Санкции", "Ставки перевозок", "Станкостроение", "Таможня", "Транзит через Россию",
    "Трансграничные платежи", "Трансграничный перевод", "Туризм", "ФТС РФ", "Цифровая валюта",
    "Цифровой финансовый актив (ЦФА)", "Экспорт в Россию", "Экспорт из Южной Кореи",
    "Экспорт из Японии", "Экспорт из Китая", "Крипта", "Крипто Валюта"
]

if not KEYWORDS:
    print("Ключевые слова не заданы. Будут отправляться все новости.")

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    print("Ошибка: не все переменные окружения заданы (токен и ID канала обязательны).")
    sys.exit(1)

# --- Конфигурация ---
MAX_ARTICLES_TO_SEND = 15          # Уменьшено для скорости
MAX_ARTICLES_PER_FEED = 5           # Уменьшено
SEND_INTERVAL_SECONDS = 20
SENT_ARTICLES_FILE = 'sent_articles.txt'
SENT_TITLES_FILE = 'sent_titles.txt'
CHANNEL_TOPIC_HEADER = "🇷🇺 Новости России"
CONTACT_LINK_TEXT = "Связаться"
CONTACT_LINK_URL = "https://t.me/tl33054"
GROUP_LINK_TEXT = "Чат"
GROUP_LINK_URL = "https://t.me/DONG8NY"

# --- Список RSS-лент (сокращён до 30 проверенных источников) ---
RSS_FEEDS = [
    "https://ria.ru/export/rss2/index.xml",
    "https://tass.ru/rss/v2.xml",
    "https://www.interfax.ru/rss.asp",
    "https://www.finmarket.ru/export/rss.asp",
    "https://www.kommersant.ru/RSS/news.xml",
    "https://www.vedomosti.ru/rss",
    "https://1prime.ru/export/rss.xml",
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
    "https://tvbrics.com/feed/",
    "https://www.rbc.ru/rss/",
    "https://lenta.ru/rss",
    "https://www.gazeta.ru/export/rss/first.xml",
    "https://expert.ru/rss/",
    "https://www.fin-gazeta.ru/rss/",
    "https://www.vestifinance.ru/rss",
    "https://www.economy.gov.ru/rss",
    "https://minpromtorg.gov.ru/rss/",
    "http://www.customs.ru/rss/",
    "https://rg.ru/rss/",
    "https://www.pnp.ru/rss/",
    "https://www.ved.gov.ru/rss/",
    "https://russian.china.org.cn/rss/business.xml",
    "https://infobrics.org/rss/",
    "https://eec.eaeunion.org/rss/",
    "https://www.logistics.ru/rss",
    "https://www.rzd-partner.ru/rss/",
    "https://www.stanok.info/rss/",
    "https://www.roprom.ru/rss/",
]

# --- Функции работы с файлами (вместо SQLite) ---
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
        return time_str

# --- Получение новостей из RSS (фильтр за последний час) ---
def get_news_from_rss():
    all_articles = []
    seen_urls = set()
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)  # можно увеличить до 6 для теста

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            print(f"Парсинг RSS: {feed_url}, найдено {len(feed.entries)} записей.")
            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                if not entry.get('link') or not entry.get('title'):
                    continue
                if entry.link in seen_urls:
                    continue

                pub_date = None
                if entry.get('published_parsed'):
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                elif entry.get('published'):
                    pass

                # Фильтр по времени (можно закомментировать для теста)
                if pub_date is None or pub_date < one_hour_ago:
                    continue

                seen_urls.add(entry.link)
                pub_date_iso = pub_date.isoformat() if pub_date else None
                description = entry.get('summary', '') or entry.get('description', '')

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

    def get_date(article):
        try:
            return datetime.fromisoformat(article.get('publishedAt', ''))
        except:
            return datetime.min

    all_articles.sort(key=get_date, reverse=True)
    print(f"Всего собрано {len(all_articles)} статей за последний час.")
    return all_articles

# --- Фильтрация по ключевым словам (без семантики) ---
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

# --- Отправка одной новости (без Playwright) ---
async def send_single_article(bot, article):
    title = article.get('title')
    url = article.get('url')
    image_url = article.get('image')
    source_name = article.get('source', {}).get('name', 'Неизвестный источник')
    if not title or not url:
        return False

    display_time = format_time(article.get('publishedAt'))

    clean_title = re.sub(r'[^\w\s]', '', title)
    words = clean_title.split()[:2]
    hashtags = " ".join([f"#{word}" for word in words if word]) if words else ""

    summary_text = article.get('description', '')
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

    # Уведомление о запуске
    try:
        print("🔍 Отправка уведомления о запуске...")
        start_message = "🔍 Начинаю поиск свежих новостей..."
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=start_message)
        print("✅ Уведомление о запуске отправлено.")
    except Exception as e:
        print(f"❌ Ошибка при отправке уведомления: {e}")

    print("Бот запущен (однократный запуск для serverless).")

    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] --- Проверка новых статей ---")

        # Загружаем уже отправленные из файлов
        sent_urls = load_sent_urls()
        sent_titles = load_sent_titles()

        print("📡 Получаем новости из RSS...")
        all_news = get_news_from_rss()
        print(f"📊 Получено {len(all_news)} статей из RSS")

        print("🔍 Фильтруем новости по ключевым словам...")
        filtered_news = filter_articles_by_keywords(all_news)
        print(f"📊 После фильтрации: {len(filtered_news)} статей")

        if not filtered_news:
            print("❌ Нет новостей после фильтрации.")
            try:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Свежих новостей по вашей теме не найдено.")
            except Exception as e:
                print(f"❌ Ошибка при отправке уведомления: {e}")
            return

        # Проверка дублей через файлы
        new_articles = []
        for article in filtered_news:
            url = article.get('url')
            title = article.get('title')
            if url not in sent_urls and title not in sent_titles:
                new_articles.append(article)

        print(f"📊 После проверки дублей: {len(new_articles)} новых статей")

        if not new_articles:
            print("❌ Новых статей (с учётом дублей) нет.")
            try:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Новых статей (с учётом уже отправленных) не найдено.")
            except Exception as e:
                print(f"❌ Ошибка при отправке уведомления: {e}")
            return

        print(f"✅ Найдено {len(new_articles)} новых статей для отправки.")

        sent_count = 0
        for article in new_articles:
            if sent_count >= MAX_ARTICLES_TO_SEND:
                print(f"Достигнут лимит отправки ({MAX_ARTICLES_TO_SEND}) за запуск.")
                break

            title = article.get('title')
            print(f"Обработка: {title}")

            if await send_single_article(bot, article):
                # Сохраняем в файлы
                save_sent_url(article.get('url'))
                save_sent_title(title)
                sent_count += 1
                print(f"Успешно отправлено ({sent_count}/{len(new_articles)} всего).")
                if sent_count < len(new_articles):
                    await asyncio.sleep(SEND_INTERVAL_SECONDS)
            else:
                print(f"Не удалось отправить: {title}")

        # Уведомление о завершении
        try:
            total_sent = len(sent_urls) + sent_count
            summary_message = f"✅ Поиск завершён. Отправлено {sent_count} новостей. Всего в истории: {total_sent}."
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary_message)
            print(f"✅ Уведомление о завершении отправлено: {sent_count} новостей")
        except Exception as e:
            print(f"❌ Ошибка при отправке уведомления о завершении: {e}")

    except Exception as e:
        print(f"❌ Критическая ошибка в main: {e}")
        import traceback
        traceback.print_exc()
        try:
            error_message = f"❌ Ошибка при выполнении поиска: {str(e)[:100]}"
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=error_message)
        except Exception as e2:
            print(f"❌ Не удалось отправить уведомление об ошибке: {e2}")

    print("--- Завершено ---")

if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)
    
