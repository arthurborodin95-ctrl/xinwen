import asyncio
import os
import sys
import re
import hashlib
import sqlite3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import telegram
import feedparser

# ---- ИМПОРТЫ ИЗ СОБСТВЕННЫХ МОДУЛЕЙ ----
from db import (
    init_db,
    is_hash_sent_today,
    mark_article_sent,
    get_total_sent,
    save_session_stats,
    get_keywords,
    get_excluded_keywords,
    get_semantic_threshold,
    get_max_articles_to_send,
    get_max_hours_old,
    get_embedding,
    save_embedding,
    get_all_topic_embeddings,
)
from yandex_ai import get_embedding as get_embedding_yandex
from news_fetcher import fetch_gnews, fetch_rss_feeds

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("❌ TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы")
    sys.exit(1)

# ---- ЗАГРУЗКА НАСТРОЕК ИЗ БД ----
init_db()
KEYWORDS = get_keywords()
EXCLUDED_KEYWORDS = get_excluded_keywords()
SEMANTIC_THRESHOLD = get_semantic_threshold()
MAX_ARTICLES_TO_SEND = get_max_articles_to_send()
MAX_HOURS_OLD = get_max_hours_old()

# ---- RSS ЛЕНТЫ (сокращённый список для скорости) ----
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
MAX_ARTICLES_PER_FEED = 20

# ---- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----

def simple_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def normalize_text(text: str) -> str:
    text = re.sub(r'[^\w\s]', '', text).lower()
    return re.sub(r'\s+', ' ', text).strip()

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = sum(x*x for x in a)**0.5
    norm_b = sum(y*y for y in b)**0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

# ---- ФУНКЦИЯ: очистка HTML для Telegram ----
def clean_telegram_html(text: str) -> str:
    """
    Удаляет все HTML-теги, кроме разрешённых Telegram.
    Оставляет: <b>, <strong>, <i>, <em>, <u>, <ins>, <s>, <strike>, <del>, <a>, <code>, <pre>, <span>
    """
    allowed_tags = ['b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'a', 'code', 'pre', 'span']
    pattern = re.compile(r'</?(?!(' + '|'.join(allowed_tags) + r')\b)[^>]+>', re.IGNORECASE)
    return pattern.sub('', text)

# ---- НОВАЯ ФУНКЦИЯ: форматирование даты публикации ----
def format_pub_date(pub_date_str: str) -> str:
    """Преобразует строку с датой в читаемый формат (день.месяц.год час:минута)."""
    if not pub_date_str:
        return "дата неизвестна"
    try:
        # Пробуем ISO-формат (например, 2026-09-07T14:30:00+00:00)
        pub_date_str = pub_date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(pub_date_str)
        # Переводим в московское время (UTC+3)
        msk_tz = timezone(timedelta(hours=3))
        dt_msk = dt.astimezone(msk_tz)
        return dt_msk.strftime('%d.%m.%Y %H:%M')
    except:
        # Если не удалось распарсить, возвращаем исходную строку
        return pub_date_str

# ---- ПОЛУЧЕНИЕ НОВОСТЕЙ ИЗ RSS ----
def get_news_from_rss():
    all_articles = []
    seen_urls = set()
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                if not entry.get('link') or not entry.get('title'):
                    continue
                if entry.link in seen_urls:
                    continue
                seen_urls.add(entry.link)
                pub_date_iso = None
                if entry.get('published_parsed'):
                    dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    pub_date_iso = dt.isoformat()
                elif entry.get('published'):
                    pub_date_iso = entry.published
                else:
                    pub_date_iso = datetime.now(timezone.utc).isoformat()
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
                all_articles.append({
                    'title': entry.title,
                    'url': entry.link,
                    'description': description,
                    'publishedAt': pub_date_iso,
                    'source': {'name': source_name},
                    'image': image_url,
                })
        except Exception as e:
            print(f"Ошибка RSS {feed_url}: {e}")
    # Сортировка по дате (новые сверху)
    all_articles.sort(
        key=lambda a: datetime.fromisoformat(a.get('publishedAt', '').replace('Z', '+00:00')) if a.get('publishedAt') else datetime.min,
        reverse=True
    )
    return all_articles

# ---- ОСНОВНАЯ ФУНКЦИЯ ----
async def main():
    init_db()
    print("✅ БД инициализирована")

    # Загружаем эталонные векторы
    topic_embeddings = get_all_topic_embeddings()
    use_semantic = bool(topic_embeddings)
    if use_semantic:
        print(f"✅ Загружено {len(topic_embeddings)} эталонных векторов.")
    else:
        print("⚠️ Семантический фильтр отключён (нет векторов).")

    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🔍 Начинаю поиск свежих новостей...")
    except Exception as e:
        print(f"⚠️ Уведомление не отправлено: {e}")

    all_news = get_news_from_rss()

    # Фильтр по времени
    time_limit = datetime.now(timezone.utc) - timedelta(hours=MAX_HOURS_OLD)
    filtered_by_time = []
    for a in all_news:
        if a.get('publishedAt'):
            try:
                pub = datetime.fromisoformat(a['publishedAt'].replace('Z', '+00:00'))
                if pub >= time_limit:
                    filtered_by_time.append(a)
            except:
                pass
    all_news = filtered_by_time
    print(f"После фильтрации времени осталось {len(all_news)} статей.")

    # Фильтр по ключевым словам и исключениям
    filtered = []
    for a in all_news:
        text = normalize_text(a['title'] + ' ' + a['description'])
        if any(kw.lower() in text for kw in KEYWORDS):
            if not any(excl.lower() in text for excl in EXCLUDED_KEYWORDS):
                filtered.append(a)
    print(f"После фильтрации слов осталось {len(filtered)} статей.")

    if not filtered:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Новостей не найдено.")
        return

    # Дедупликация по хешу
    new_articles = []
    for a in filtered:
        raw = normalize_text(a['title'] + ' ' + a['description'])[:500]
        h = simple_hash(raw)
        if not is_hash_sent_today(h):
            a['_hash'] = h
            new_articles.append(a)
    print(f"Новых статей: {len(new_articles)}")

    if not new_articles:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Новых статей нет (все уже были сегодня).")
        return

    # Семантическая фильтрация (если включена)
    final_articles = []
    semantic_passed = 0
    semantic_failed = 0
    similarities = []
    if use_semantic:
        for a in new_articles[:30]:
            text = normalize_text(a['title'] + ' ' + a['description'])[:500]
            h = simple_hash(text)
            emb = get_embedding(h)
            if emb is None:
                emb = get_embedding_yandex(text)
                if emb:
                    save_embedding(h, emb)
                else:
                    semantic_failed += 1
                    continue
            max_sim = max(cosine_similarity(emb, vec) for vec in topic_embeddings.values())
            similarities.append(max_sim)
            if max_sim >= SEMANTIC_THRESHOLD:
                final_articles.append(a)
                semantic_passed += 1
            else:
                semantic_failed += 1
        new_articles = final_articles
        print(f"Семантика: принято {semantic_passed}, отклонено {semantic_failed}")
        if not new_articles:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Все новости отклонены семантикой.")
            return

    # ---- ОТПРАВКА НОВОСТЕЙ (С ДАТОЙ И ВРЕМЕНЕМ) ----
    sent_count = 0
    for a in new_articles[:MAX_ARTICLES_TO_SEND]:
        # Очищаем описание от недопустимых тегов
        description = a.get('description', '') or ''
        description = clean_telegram_html(description)
        if len(description) > 500:
            description = description[:500] + '...'

        # Форматируем дату публикации
        pub_date = format_pub_date(a.get('publishedAt', ''))

        # Формируем сообщение с датой
        caption = f"<b>{a['title']}</b>\n\n{description}\n\n📅 {pub_date}\n🔗 <a href='{a['url']}'>Читать полностью</a>"

        print(f"📤 Отправляю: {a['title'][:50]}...")

        try:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=caption,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            mark_article_sent(a['url'], a['title'], a['source'].get('name', ''), a.get('_hash', ''))
            sent_count += 1
            print(f"   ✅ Отправлено ({sent_count})")
        except Exception as e:
            print(f"   ❌ Ошибка отправки: {e}")
            # Попытка отправить без HTML-разметки
            try:
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=caption,
                    parse_mode=None,
                    disable_web_page_preview=True
                )
                mark_article_sent(a['url'], a['title'], a['source'].get('name', ''), a.get('_hash', ''))
                sent_count += 1
                print(f"   ✅ Отправлено (plain text) ({sent_count})")
            except Exception as e2:
                print(f"   ❌ Критическая ошибка отправки: {e2}")

    # ---- УВЕДОМЛЕНИЕ О ЗАВЕРШЕНИИ ----
    avg_sim = sum(similarities) / len(similarities) if similarities else 0.0
    save_session_stats(
        total_found=len(all_news),
        total_filtered=len(filtered),
        total_sent=sent_count,
        semantic_passed=semantic_passed,
        semantic_failed=semantic_failed,
        avg_similarity=avg_sim,
        threshold=SEMANTIC_THRESHOLD
    )
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Отправлено {sent_count} новостей.")

if __name__ == '__main__':
    asyncio.run(main())
