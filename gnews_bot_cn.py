import requests
import telegram
import time
import asyncio
import os
import re
import sys
import hashlib
from dotenv import load_dotenv
from telegram.constants import ParseMode
from datetime import datetime, timezone, timedelta
import feedparser

# --- ИМПОРТЫ ИЗ SQLite-МОДУЛЯ ---
from db import (
    init_db,
    is_hash_sent_today,        # Новая функция проверки по хешу
    mark_article_sent,
    get_total_sent,
    save_session_stats,
    clear_old_entries,
    get_embedding,
    save_embedding,
    get_all_topic_embeddings,
    save_topic_embedding,
    clear_topic_embeddings
)
from yandex_ai import get_embedding as get_embedding_yandex

# --- Загрузка переменных окружения ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- ТЕМАТИЧЕСКИЕ ГРУППЫ КЛЮЧЕВЫХ СЛОВ ---
TOPIC_GROUPS = {
    'trade': ['импорт', 'экспорт', 'пошлины', 'таможня', 'вэд', 'еаэс', 'бартер'],
    'logistics': ['перевозки', 'транзит', 'логистика', 'груз', 'транспорт'],
    'sanctions': ['санкции', 'ограничения', 'эмбарго', 'запрет поставок'],
    'china': ['Китай', 'китайская экономика', 'из Китая', 'импорт из Китая', 'экспорт в Китай'],
    'production': ['производство', 'запущено производство', 'станкостроение', 'локализация'],
}

# --- ОБЩИЙ СПИСОК КЛЮЧЕВЫХ СЛОВ ---
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

# --- КЛЮЧЕВЫЕ СЛОВА ИСКЛЮЧЕНИЙ ---
EXCLUDED_KEYWORDS = [
    "нефть", "нефтяной", "нефтепродукты",
    "газ", "газовый", "сжиженный газ", "спг",
    "алюминий", "алюминиевый",
    "сырьё", "сырьевой", "промышленное сырье",
    "металл", "металлургия", "руда",
    "добыча", "добывающий",
    "уголь", "угледобыча",
]

if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    print("Ошибка: не все переменные окружения заданы.")
    sys.exit(1)

# --- КОНФИГУРАЦИЯ ---
MAX_ARTICLES_TO_SEND = 30
SEND_INTERVAL_SECONDS = 20
CHANNEL_TOPIC_HEADER = "🇷🇺 Новости России"
CONTACT_LINK_TEXT = "Связаться"
CONTACT_LINK_URL = "https://t.me/tl33054"
GROUP_LINK_TEXT = "Чат"
GROUP_LINK_URL = "https://t.me/DONG8NY"
SEMANTIC_THRESHOLD = 0.7
MAX_SEMANTIC_CHECKS = 30
MAX_HOURS_OLD = 6

# --- RSS ЛЕНТЫ ---
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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

def simple_hash(text: str) -> str:
    """Вычисляет MD5-хеш строки."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def cosine_similarity(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = sum(x*x for x in a)**0.5
    norm_b = sum(y*y for y in b)**0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# ---- НОВАЯ ФУНКЦИЯ: нормализация текста для фильтрации ----
def normalize_text(text: str) -> str:
    """Удаляет знаки препинания и приводит к нижнему регистру."""
    text = re.sub(r'[^\w\s]', '', text)
    return text.lower()

# --- ПОЛУЧЕНИЕ НОВОСТЕЙ ИЗ RSS С ФИЛЬТРОМ ПО ВРЕМЕНИ ---

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

    # ---- ФИЛЬТР ПО ВРЕМЕНИ ----
    time_limit = datetime.now(timezone.utc) - timedelta(hours=MAX_HOURS_OLD)
    filtered_by_time = []
    for article in all_articles:
        pub_date = article.get('publishedAt')
        if pub_date:
            try:
                pub_str = pub_date.replace('Z', '+00:00')
                pub_dt = datetime.fromisoformat(pub_str)
                if pub_dt >= time_limit:
                    filtered_by_time.append(article)
            except:
                pass
    all_articles = filtered_by_time
    print(f"После фильтрации по времени (последние {MAX_HOURS_OLD} ч.) осталось {len(all_articles)} статей.")
    return all_articles

# --- ФИЛЬТРАЦИЯ ПО КЛЮЧЕВЫМ СЛОВАМ С ИСКЛЮЧЕНИЯМИ (УЛУЧШЕННАЯ) ---

def filter_articles_by_keywords_and_exclusions(articles):
    if not KEYWORDS:
        return articles

    filtered = []
    for article in articles:
        title = article.get("title", "")
        description = article.get("description", "")
        raw_content = title + " " + description
        content = normalize_text(raw_content)   # нормализуем для поиска

        has_keyword = any(kw.lower() in content for kw in KEYWORDS)
        if not has_keyword:
            continue

        if EXCLUDED_KEYWORDS:
            has_excluded = any(excl.lower() in content for excl in EXCLUDED_KEYWORDS)
            if has_excluded:
                # Логируем для отладки
                print(f"⏭️ Исключена: {title[:50]} (содержит слово исключения)")
                continue

        filtered.append(article)

    print(f"После фильтрации (ключевые слова + исключения) осталось {len(filtered)} из {len(articles)} статей.")
    return filtered

# --- ОТПРАВКА ОДНОЙ НОВОСТИ ---

async def send_single_article(bot, article, pub_time: str, summary: str):
    title = article.get('title')
    url = article.get('url')
    image_url = article.get('image')
    source_name = article.get('source', {}).get('name', 'Неизвестный источник')
    if not title or not url:
        return False

    display_time = format_time(pub_time) if pub_time else format_time(article.get('publishedAt'))
    clean_title = re.sub(r'[^\w\s]', '', title)
    words = clean_title.split()[:2]
    hashtags = " ".join([f"#{word}" for word in words if word]) if words else ""

    summary_text = summary if summary else article.get('description', '')
    # Удаляем недопустимые HTML-теги (например, <p>)
    summary_text = re.sub(r'</?p>', '', summary_text)

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
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=caption, parse_mode=None, disable_web_page_preview=True)
            return True
        except Exception as fallback_e:
            print(f"Не удалось отправить даже plain текст: {fallback_e}")
            return False

# --- ПОЛУЧЕНИЕ ЭТАЛОННЫХ ВЕКТОРОВ ---

def get_or_compute_topic_embeddings():
    stored = get_all_topic_embeddings()
    if stored:
        print(f"✅ Загружены эталонные векторы для {len(stored)} групп из БД.")
        return stored

    print("🧠 Вычисляем эталонные векторы для тематических групп...")
    embeddings = {}
    for group, words in TOPIC_GROUPS.items():
        text = ' '.join(words)
        emb = get_embedding_yandex(text)
        if emb:
            embeddings[group] = emb
            save_topic_embedding(group, emb)
            print(f"  ✅ Группа '{group}': вектор получен (размерность {len(emb)})")
        else:
            print(f"  ❌ Группа '{group}': не удалось получить вектор")
    return embeddings

# --- ОСНОВНАЯ ФУНКЦИЯ (С ДЕДУПЛИКАЦИЕЙ ПО ХЕШУ) ---

async def main():
    start_time = time.time()

    # ---- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ----
    init_db()
    clear_old_entries(days=7)  # очищаем старые записи
    print("✅ База данных инициализирована.")

    # ---- ЗАГРУЗКА ЭТАЛОННЫХ ВЕКТОРОВ ----
    topic_embeddings = get_or_compute_topic_embeddings()
    use_semantic = bool(topic_embeddings)
    if use_semantic:
        print(f"✅ Загружено {len(topic_embeddings)} эталонных векторов.")
    else:
        print("⚠️ Семантический фильтр отключён.")

    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    print("Бот запущен (однократный запуск для serverless).")

    # Уведомление о начале
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="🔍 Начинаю поиск свежих новостей...")
        print("✅ Уведомление о начале поиска отправлено.")
    except Exception as e:
        print(f"⚠️ Не удалось отправить уведомление о начале: {e}")

    try:
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] --- Проверка новых статей ---")

        all_news = get_news_from_rss()
        filtered_news = filter_articles_by_keywords_and_exclusions(all_news)

        if not filtered_news:
            print("Нет новостей после фильтрации.")
            try:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Свежих новостей по вашей теме не найдено.")
            except Exception as e:
                print(f"⚠️ Не удалось отправить уведомление: {e}")
            save_session_stats(
                total_found=len(all_news),
                total_filtered=0,
                total_sent=0,
                semantic_passed=0,
                semantic_failed=0,
                avg_similarity=0.0,
                threshold=SEMANTIC_THRESHOLD if use_semantic else 0.0,
                extra_data={'sources': RSS_FEEDS[:5]}
            )
            return

        # ---- 1. ДЕДУПЛИКАЦИЯ ПО ХЕШУ (ЗАГОЛОВОК + ОПИСАНИЕ) ----
        new_articles = []
        for article in filtered_news:
            title = article.get('title')
            description = article.get('description', '')
            if not title:
                continue
            text_for_hash = (title + ' ' + description)[:500]
            hash_value = simple_hash(text_for_hash)
            if not is_hash_sent_today(hash_value):
                article['_hash'] = hash_value   # сохраняем хеш в статье
                new_articles.append(article)

        if not new_articles:
            print("Новых статей (с учётом дублей) нет.")
            try:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Новых статей (с учётом уже отправленных) не найдено.")
            except Exception as e:
                print(f"⚠️ Не удалось отправить уведомление: {e}")
            save_session_stats(
                total_found=len(all_news),
                total_filtered=len(filtered_news),
                total_sent=0,
                semantic_passed=0,
                semantic_failed=0,
                avg_similarity=0.0,
                threshold=SEMANTIC_THRESHOLD if use_semantic else 0.0,
                extra_data={'sources': RSS_FEEDS[:5]}
            )
            return

        # ---- 2. СЕМАНТИЧЕСКАЯ ФИЛЬТРАЦИЯ (ТОЛЬКО ДЛЯ НОВЫХ СТАТЕЙ) ----
        semantic_passed = 0
        semantic_failed = 0
        similarities = []
        final_articles = []

        if use_semantic:
            articles_to_check = new_articles[:MAX_SEMANTIC_CHECKS]
            if len(new_articles) > MAX_SEMANTIC_CHECKS:
                print(f"⚠️ Слишком много новых статей ({len(new_articles)}), проверяем только первые {MAX_SEMANTIC_CHECKS}.")

            print(f"🧠 Применяем семантическую фильтрацию для {len(articles_to_check)} статей...")
            for article in articles_to_check:
                text = (article['title'] + ' ' + article['description'])[:500]
                h = simple_hash(text)
                emb = get_embedding(h)
                if emb is None:
                    emb = get_embedding_yandex(text)
                    if emb:
                        save_embedding(h, emb)
                    else:
                        semantic_failed += 1
                        continue

                max_sim = 0.0
                for group, topic_vec in topic_embeddings.items():
                    sim = cosine_similarity(emb, topic_vec)
                    if sim > max_sim:
                        max_sim = sim

                similarities.append(max_sim)
                if max_sim >= SEMANTIC_THRESHOLD:
                    final_articles.append(article)
                    semantic_passed += 1
                else:
                    semantic_failed += 1

            print(f"📊 Семантика: принято {semantic_passed}, отклонено {semantic_failed}")
            avg_sim = sum(similarities) / len(similarities) if similarities else 0.0
            print(f"📊 Средняя схожесть: {avg_sim:.3f}")

            if not final_articles:
                print("❌ Все новые статьи отклонены семантическим фильтром.")
                try:
                    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 Все новые статьи не прошли семантическую проверку.")
                except Exception as e:
                    print(f"⚠️ Не удалось отправить уведомление: {e}")
                save_session_stats(
                    total_found=len(all_news),
                    total_filtered=len(filtered_news),
                    total_sent=0,
                    semantic_passed=semantic_passed,
                    semantic_failed=semantic_failed,
                    avg_similarity=avg_sim,
                    threshold=SEMANTIC_THRESHOLD,
                    extra_data={'sources': RSS_FEEDS[:5]}
                )
                return

            new_articles = final_articles
        else:
            avg_sim = 0.0

        print(f"✅ Найдено {len(new_articles)} статей для отправки после всех фильтров.")

        # ---- 3. ОТПРАВКА НОВОСТЕЙ (С СОХРАНЕНИЕМ ХЕША В SQLite) ----
        sent_count = 0
        sent_titles_this_run = set()
        sent_articles = []

        for article in new_articles:
            if sent_count >= MAX_ARTICLES_TO_SEND:
                print(f"Достигнут лимит отправки ({MAX_ARTICLES_TO_SEND}) за запуск.")
                break

            title = article.get('title')
            if title in sent_titles_this_run:
                print(f"Дубликат заголовка в этом запуске: {title}, пропускаем.")
                # Сохраняем, чтобы не проверять снова (хеш уже есть)
                mark_article_sent(
                    article.get('url'),
                    title,
                    article.get('source', {}).get('name', ''),
                    article.get('_hash', '')
                )
                continue

            print(f"Обработка: {title}")

            pub_time = article.get('publishedAt', '')
            summary = article.get('description', '')

            if await send_single_article(bot, article, pub_time, summary):
                # ---- СОХРАНЯЕМ В SQLite (с хешем) ----
                mark_article_sent(
                    article.get('url'),
                    title,
                    article.get('source', {}).get('name', ''),
                    article.get('_hash', '')
                )
                sent_titles_this_run.add(title)
                sent_count += 1
                sent_articles.append(article)
                print(f"Успешно отправлено ({sent_count}/{MAX_ARTICLES_TO_SEND}).")
                if sent_count < MAX_ARTICLES_TO_SEND and sent_count < len(new_articles):
                    await asyncio.sleep(SEND_INTERVAL_SECONDS)
            else:
                print(f"Не удалось отправить: {title}")

        # ---- 4. ИТОГОВЫЙ ОТЧЁТ ----
        if sent_articles:
            try:
                skipped = [a['title'] for a in new_articles if a not in sent_articles]
                from ai_analyzer import generate_report
                report = await generate_report(
                    total_found=len(all_news),
                    total_filtered=len(filtered_news),
                    total_sent=len(sent_articles),
                    sources_checked=RSS_FEEDS,
                    skipped_titles=skipped[:5],
                    errors=[]
                )
                if report:
                    await bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=f"📊 Итоговый отчёт:\n{report}",
                        parse_mode=ParseMode.HTML
                    )
                    print("✅ Итоговый отчёт отправлен.")
            except Exception as e:
                print(f"❌ Ошибка при генерации итогового отчёта: {e}")

        # ---- 5. УВЕДОМЛЕНИЕ О ЗАВЕРШЕНИИ ----
        try:
            total_sent = get_total_sent()
            stats_message = (
                f"✅ Поиск завершён.\n"
                f"📊 Статистика:\n"
                f"  - Найдено всего: {len(all_news)}\n"
                f"  - После фильтрации: {len(filtered_news)}\n"
                f"  - Отправлено (новых): {sent_count}\n"
                f"  - Всего в БД: {total_sent}\n"
                f"  - Семантика: принято {semantic_passed}, отклонено {semantic_failed}"
            )
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=stats_message)
            print("✅ Уведомление о завершении отправлено.")
        except Exception as e:
            print(f"⚠️ Не удалось отправить уведомление о завершении: {e}")

        # ---- 6. СОХРАНЕНИЕ СТАТИСТИКИ В БД ----
        save_session_stats(
            total_found=len(all_news),
            total_filtered=len(filtered_news),
            total_sent=sent_count,
            semantic_passed=semantic_passed,
            semantic_failed=semantic_failed,
            avg_similarity=avg_sim,
            threshold=SEMANTIC_THRESHOLD if use_semantic else 0.0,
            extra_data={'sources': RSS_FEEDS[:5]}
        )

    except Exception as e:
        print(f"Критическая ошибка в main: {e}")
        try:
            error_message = f"❌ Произошла ошибка при выполнении поиска: {str(e)[:100]}"
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=error_message)
        except Exception as e2:
            print(f"⚠️ Не удалось отправить уведомление об ошибке: {e2}")
    finally:
        elapsed = time.time() - start_time
        print(f"--- Завершено за {elapsed:.2f} секунд ---")

if __name__ == '__main__':
    asyncio.run(main())
    sys.exit(0)