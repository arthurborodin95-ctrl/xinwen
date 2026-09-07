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

# --- ИМПОРТЫ ИЗ МОДУЛЕЙ ---
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
    save_topic_embedding,
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

# ---- ID пользователей для отправки (можно расширить) ----
# Если хотите отправлять нескольким пользователям, добавьте их ID в список
# CHAT_IDS = [int(TELEGRAM_CHAT_ID), 987654321]  # раскомментируйте и добавьте
CHAT_IDS = [int(TELEGRAM_CHAT_ID)]  # пока только один

# ---- RSS ЛЕНТЫ ----
RSS_FEEDS = [
    # ===== Основные СМИ =====
    "https://ria.ru/export/rss2/index.xml",              # РИА Новости
    "https://tass.ru/rss/v2.xml",                        # ТАСС
    "https://www.interfax.ru/rss.asp",                   # Интерфакс
    "https://www.finmarket.ru/export/rss.asp",           # Финмаркет
    "https://www.kommersant.ru/RSS/news.xml",            # Коммерсантъ
    "https://www.vedomosti.ru/rss",                      # Ведомости
    "https://1prime.ru/export/rss.xml",                  # Прайм
    "https://www.forbes.ru/rss/all",                     # Forbes Russia
    "https://iz.ru/xml/rss/all.xml",                     # Известия
    "https://www.rbc.ru/rss/",                           # РБК
    "https://lenta.ru/rss",                              # Lenta.ru
    "https://www.gazeta.ru/export/rss/first.xml",        # Газета.ru
    "https://expert.ru/rss/",                            # Эксперт
    "https://www.fin-gazeta.ru/rss/",                    # Финансовая газета
    "https://www.vestifinance.ru/rss",                   # Вести Финанс
    "https://rg.ru/rss/",                                # Российская газета
    "https://www.pnp.ru/rss/",                           # Парламентская газета

    # ===== Специализированные (экономика, ВЭД, логистика) =====
    "https://www.tks.ru/law.rss",                        # TKS.ru (законодательство)
    "https://www.tks.ru/nearby.rss",                     # TKS.ru (смежные темы)
    "https://trans.ru/rss/news",                         # Trans.ru (логистика)
    "https://www.infranews.ru/feed/",                    # Infranews
    "https://www.tourdom.ru/rss/",                       # Tourdom (туризм)
    "https://www.autostat.ru/export/rss/",               # Автостат
    "https://morvesti.ru/rss/",                          # Морские вести
    "https://portnews.ru/rss/",                          # Portnews
    "https://seanews.ru/feed/",                          # Seanews
    "https://primpress.ru/rss/",                         # Primpress
    "https://www.cnews.ru/news/rss",                     # CNews
    "https://www.comnews.ru/rss",                        # ComNews
    "https://www.ixbt.com/export/news.rss",              # IXBT (технологии)
    "https://biang.ru/rss/",                             # Biang.ru
    "https://www.eastrussia.ru/feed/",                   # EastRussia
    "https://bigasia.ru/feed/",                          # BigAsia
    "https://tvbrics.com/feed/",                         # TV BRICS
    "https://infobrics.org/rss/",                        # BRICS Business
    "https://eec.eaeunion.org/rss/",                     # ЕАЭС / ЕЭК

    # ===== Китай и Азия =====
    "http://russian.news.cn/rss/news.xml",               # Синьхуа (русская версия)
    "http://russian.china.org.cn/rss/feed.xml",          # Китайский инфоцентр
    "http://russian.people.com.cn/rss/feed.xml",         # People's Daily
    "https://russian.china.org.cn/rss/business.xml",     # Китайский бизнес
    "https://www.scmp.com/rss/",                         # South China Morning Post
    "https://rsshub.app/cnbc/rss/",                      # CNBC (через RSSHub)

    # ===== Официальные государственные =====
    "http://www.cbr.ru/rss/RssNews",                     # ЦБ РФ (новости)
    "http://www.cbr.ru/rss/RssPress",                    # ЦБ РФ (пресс-релизы)
    "https://www.economy.gov.ru/rss",                    # Минэкономразвития
    "https://minpromtorg.gov.ru/rss/",                   # Минпромторг
    "http://www.customs.ru/rss/",                        # ФТС РФ
    "https://www.ved.gov.ru/rss/",                       # Журнал "Внешняя торговля"

    # ===== Логистика и промышленность =====
    "https://www.logistics.ru/rss",                      # Логистика
    "https://www.rzd-partner.ru/rss/",                   # РЖД-Партнёр
    "https://www.stanok.info/rss/",                      # Станкостроение
    "https://www.roprom.ru/rss/",                        # Российская промышленность
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

def format_time(pub_date_str: str) -> str:
    """Преобразует ISO-дату в читаемый формат (Москва)."""
    if not pub_date_str:
        return "неизвестно"
    try:
        dt = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
        msk_tz = timezone(timedelta(hours=3))
        dt_msk = dt.astimezone(msk_tz)
        return dt_msk.strftime('%d.%m.%Y %H:%M')
    except Exception:
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
    def get_date(a):
        try:
            return datetime.fromisoformat(a['publishedAt'].replace('Z', '+00:00'))
        except:
            return datetime.min
    all_articles.sort(key=get_date, reverse=True)
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

    # Уведомление о начале (отправляем всем пользователям)
    for chat_id in CHAT_IDS:
        try:
            await bot.send_message(chat_id=chat_id, text="🔍 Начинаю поиск свежих новостей...")
        except Exception as e:
            print(f"⚠️ Уведомление для {chat_id} не отправлено: {e}")

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
        for chat_id in CHAT_IDS:
            try:
                await bot.send_message(chat_id=chat_id, text="📭 Новостей не найдено.")
            except Exception as e:
                print(f"⚠️ Уведомление для {chat_id} не отправлено: {e}")
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
        for chat_id in CHAT_IDS:
            try:
                await bot.send_message(chat_id=chat_id, text="📭 Новых статей нет (все уже были сегодня).")
            except Exception as e:
                print(f"⚠️ Уведомление для {chat_id} не отправлено: {e}")
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
            for chat_id in CHAT_IDS:
                try:
                    await bot.send_message(chat_id=chat_id, text="📭 Все новости отклонены семантикой.")
                except Exception as e:
                    print(f"⚠️ Уведомление для {chat_id} не отправлено: {e}")
            return

    # Отправка новостей
    sent_count = 0
    for a in new_articles[:MAX_ARTICLES_TO_SEND]:
        source = a.get('source', {}).get('name', 'Неизвестный источник')
        pub_time = format_time(a.get('publishedAt', ''))

        # Формируем сообщение с источником и временем
        caption = (
            f"<b>{a['title']}</b>\n\n"
            f"{a['description'][:500]}\n\n"
            f"📰 Источник: {source}\n"
            f"🕒 {pub_time}\n\n"
            f"🔗 <a href='{a['url']}'>Читать полностью</a>"
        )

        for chat_id in CHAT_IDS:
            try:
                await bot.send_message(chat_id=chat_id, text=caption, parse_mode='HTML', disable_web_page_preview=True)
                # Сохраняем хеш только один раз (неважно, для какого чата)
                if chat_id == CHAT_IDS[0]:
                    mark_article_sent(a['url'], a['title'], source, a.get('_hash', ''))
            except Exception as e:
                print(f"Ошибка отправки для {chat_id}: {e}")
        sent_count += 1

    avg_sim = sum(similarities)/len(similarities) if similarities else 0.0
    save_session_stats(
        total_found=len(all_news),
        total_filtered=len(filtered),
        total_sent=sent_count,
        semantic_passed=semantic_passed,
        semantic_failed=semantic_failed,
        avg_similarity=avg_sim,
        threshold=SEMANTIC_THRESHOLD
    )

    # Уведомление о завершении
    for chat_id in CHAT_IDS:
        try:
            await bot.send_message(chat_id=chat_id, text=f"✅ Отправлено {sent_count} новостей.")
        except Exception as e:
            print(f"⚠️ Уведомление для {chat_id} не отправлено: {e}")

if __name__ == '__main__':
    asyncio.run(main())