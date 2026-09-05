import asyncio
import logging
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Импорты из ваших модулей
from db import init_db, is_hash_sent_today, mark_article_sent, get_total_sent
from yandex_ai import call_yandex_gpt, get_embedding
from news_fetcher import fetch_gnews, fetch_rss_feeds
# Импортируем функции из main.py (или скопируйте их сюда, если нужно)
from main import (
    get_news_from_rss,
    filter_articles_by_keywords_and_exclusions,
    simple_hash,
    normalize_text,
    normalize_for_hash,
    SEMANTIC_THRESHOLD,
    MAX_HOURS_OLD,
    RSS_FEEDS,
    KEYWORDS,
    EXCLUDED_KEYWORDS
)

import os
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан")

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Хранилище контекста диалогов (в памяти)
user_context = {}

# Инициализация БД (если ещё не создана)
init_db()

# --- Вспомогательные функции ---

def format_news_summary(articles, max_items=10):
    """Форматирует список статей для отправки."""
    if not articles:
        return "Новостей не найдено."
    lines = []
    for i, a in enumerate(articles[:max_items], 1):
        title = a.get('title', 'Без заголовка')
        url = a.get('url', '#')
        source = a.get('source', {}).get('name', 'Неизвестный источник')
        # Краткое описание (первые 100 символов)
        desc = a.get('description', '')
        if desc:
            desc = desc[:100] + ('...' if len(desc) > 100 else '')
        lines.append(f"{i}. **{title}**\n   [{source}]({url})\n   _{desc}_" if desc else f"{i}. **{title}**\n   [{source}]({url})")
    return "\n\n".join(lines)

async def search_news(query: str) -> str:
    """Ищет новости по запросу и возвращает отформатированный результат."""
    # Используем GNews (более точный поиск по ключевым словам)
    articles = fetch_gnews(query, max_articles=20)
    if not articles:
        # Если GNews не вернул, пробуем RSS с фильтром
        all_news = get_news_from_rss()
        keywords_from_query = query.split()
        filtered = []
        for article in all_news:
            title = article.get('title', '')
            desc = article.get('description', '')
            text = (title + ' ' + desc).lower()
            if any(kw.lower() in text for kw in keywords_from_query):
                filtered.append(article)
        articles = filtered
    if not articles:
        return "По вашему запросу новостей не найдено."
    return format_news_summary(articles, max_items=10)

async def analyze_news_content(text: str) -> str:
    """Анализирует переданный текст новости через YandexGPT."""
    if not text or len(text.strip()) < 20:
        return "Текст слишком короткий для анализа."
    prompt = f"""
Ты — эксперт-аналитик новостей. Проанализируй следующий текст и дай краткую экспертную оценку:

{text}

В ответе укажи:
1. Основной смысл новости.
2. Кому она адресована (аудитория).
3. Возможные последствия или значение.
Будь краток, но информативен.
"""
    response = call_yandex_gpt(prompt, max_tokens=400, temperature=0.4)
    return response if response else "Не удалось проанализировать новость."

async def ask_agent(question: str, user_id: int) -> str:
    """Обрабатывает вопрос через YandexGPT с учётом контекста."""
    history = user_context.get(user_id, [])
    # Ограничиваем историю последними 10 сообщениями
    context_text = "\n".join(history[-10:]) if history else ""
    prompt = f"""
Ты — интеллектуальный помощник, который отвечает на вопросы пользователя на основе своих знаний и новостного контекста.

История диалога:
{context_text}

Вопрос пользователя: {question}

Дай развёрнутый, но лаконичный ответ. Если вопрос касается новостей, экономики, логистики, постарайся дать актуальную информацию и, если нужно, предложи поискать новости через команду /search.
"""
    response = call_yandex_gpt(prompt, max_tokens=600, temperature=0.7)
    if not response:
        return "Извините, не удалось обработать запрос. Попробуйте позже."
    # Сохраняем в историю
    history.append(f"Пользователь: {question}")
    history.append(f"Бот: {response}")
    user_context[user_id] = history[-20:]  # храним последние 20 записей
    return response

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Привет! Я — ваш персональный новостной агент.\n\n"
        "Я умею:\n"
        "- Отвечать на вопросы (/ask <вопрос>)\n"
        "- Искать новости по запросу (/search <запрос>)\n"
        "- Анализировать новости (/analyze <текст или ссылка>)\n"
        "- Показывать статистику (/stats)\n"
        "- Учиться на ваших оценках (/feedback like|dislike)\n\n"
        "Просто напишите мне вопрос, и я постараюсь помочь!"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Укажите запрос: /search <текст>")
        return
    await update.message.reply_text("🔍 Ищу новости...")
    result = await search_news(query)
    await update.message.reply_text(result, parse_mode='Markdown', disable_web_page_preview=True)

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = ' '.join(context.args)
    if not question:
        await update.message.reply_text("Задайте вопрос: /ask <текст вопроса>")
        return
    user_id = update.effective_user.id
    await update.message.reply_text("🤔 Думаю...")
    answer = await ask_agent(question, user_id)
    # Кнопки для оценки
    keyboard = [
        [InlineKeyboardButton("👍 Полезно", callback_data='feedback_like'),
         InlineKeyboardButton("👎 Бесполезно", callback_data='feedback_dislike')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(answer, reply_markup=reply_markup)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если есть аргумент – используем его как текст для анализа
    text = ' '.join(context.args)
    if not text:
        # Если нет аргумента, пробуем взять последнюю новость из контекста (можно из БД)
        # Для простоты предложим пользователю вставить текст.
        await update.message.reply_text("Введите текст новости для анализа: /analyze <текст>")
        return
    await update.message.reply_text("🧐 Анализирую...")
    analysis = await analyze_news_content(text)
    await update.message.reply_text(analysis)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = get_total_sent()
    # Дополнительно можно посчитать количество за сегодня
    await update.message.reply_text(f"📊 Всего отправлено новостей за всё время: {total}")

async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    # Здесь можно сохранить оценку в БД (например, в таблицу user_feedback)
    if data == 'feedback_like':
        await query.edit_message_text(text="✅ Спасибо за положительную оценку!")
        # Здесь: сохранить +1 в рейтинг
    elif data == 'feedback_dislike':
        await query.edit_message_text(text="😕 Спасибо за обратную связь, я постараюсь улучшиться!")
        # Здесь: сохранить -1

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычного текста (не команды) — воспринимаем как вопрос."""
    text = update.message.text
    user_id = update.effective_user.id
    await update.message.reply_text("🤔 Анализирую ваш запрос...")
    answer = await ask_agent(text, user_id)
    keyboard = [[InlineKeyboardButton("👍 Полезно", callback_data='feedback_like'),
                 InlineKeyboardButton("👎 Бесполезно", callback_data='feedback_dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(answer, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

def main():
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("ask", ask))
    application.add_handler(CommandHandler("analyze", analyze))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CallbackQueryHandler(feedback_callback, pattern='feedback_'))

    # Обработчик обычных сообщений (не команд)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запускаем бота в режиме polling
    print("🚀 Запуск интерактивного агента...")
    application.run_polling()

if __name__ == '__main__':
    main()
