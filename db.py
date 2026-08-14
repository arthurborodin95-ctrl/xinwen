import sqlite3
import json

DB_FILE = 'news.db'

# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ====================

def init_db():
    """Создаёт все необходимые таблицы и индексы при первом запуске."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. Таблица отправленных статей (была)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            source TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON sent_articles (url)')

    # 2. Таблица кэша эмбеддингов (новая)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS article_embeddings (
            hash TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,   -- храним как JSON-строку (массив чисел)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON article_embeddings (created_at)')

    # 3. Таблица истории сессий (новая)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_found INTEGER,
            total_filtered INTEGER,
            total_sent INTEGER,
            semantic_passed INTEGER,
            semantic_failed INTEGER,
            avg_similarity REAL,
            threshold REAL,
            extra_data TEXT   -- JSON для дополнительных данных (например, список источников)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON session_stats (timestamp)')

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована (все таблицы созданы).")


# ==================== РАБОТА С ОТПРАВЛЕННЫМИ СТАТЬЯМИ ====================

def is_article_sent(url: str) -> bool:
    """Проверяет, отправлялась ли уже статья с таким URL."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM sent_articles WHERE url = ?', (url,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def mark_article_sent(url: str, title: str, source: str = ''):
    """Сохраняет отправленную статью в БД."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO sent_articles (url, title, source) VALUES (?, ?, ?)',
        (url, title, source)
    )
    conn.commit()
    conn.close()

def get_total_sent() -> int:
    """Возвращает общее количество отправленных статей."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sent_articles')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def clear_old_entries(days: int = 30):
    """Удаляет отправленные статьи старше указанного количества дней."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM sent_articles WHERE sent_at < datetime("now", ?)',
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()


# ==================== КЭШИРОВАНИЕ ЭМБЕДДИНГОВ ====================

def get_embedding(text_hash: str):
    """
    Возвращает сохранённый эмбеддинг по хешу текста,
    если он есть в кэше. Иначе возвращает None.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT embedding FROM article_embeddings WHERE hash = ?', (text_hash,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])  # возвращаем список чисел
    return None

def save_embedding(text_hash: str, embedding: list):
    """Сохраняет эмбеддинг (список чисел) в кэш по хешу текста."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO article_embeddings (hash, embedding) VALUES (?, ?)',
        (text_hash, json.dumps(embedding))
    )
    conn.commit()
    conn.close()

def clear_old_embeddings(days: int = 30):
    """Удаляет старые эмбеддинги (экономия места)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM article_embeddings WHERE created_at < datetime("now", ?)',
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()


# ==================== ИСТОРИЯ СЕССИЙ (ДЛЯ АНАЛИТИКИ) ====================

def save_session_stats(
    total_found: int,
    total_filtered: int,
    total_sent: int,
    semantic_passed: int,
    semantic_failed: int,
    avg_similarity: float,
    threshold: float,
    extra_data: dict = None
):
    """
    Сохраняет статистику сессии в таблицу session_stats.
    extra_data — опциональный словарь с дополнительными данными (например, список источников).
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO session_stats (
            total_found, total_filtered, total_sent,
            semantic_passed, semantic_failed, avg_similarity,
            threshold, extra_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            total_found,
            total_filtered,
            total_sent,
            semantic_passed,
            semantic_failed,
            avg_similarity,
            threshold,
            json.dumps(extra_data) if extra_data else None
        )
    )
    conn.commit()
    conn.close()

def get_recent_stats(limit: int = 10):
    """
    Возвращает последние N записей статистики сессий (по убыванию времени).
    Используется для анализа динамики и адаптивного порога.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        '''
        SELECT timestamp, total_found, total_filtered, total_sent,
               semantic_passed, semantic_failed, avg_similarity, threshold
        FROM session_stats
        ORDER BY timestamp DESC
        LIMIT ?
        ''',
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_last_n_avg_similarity(n: int = 5):
    """
    Возвращает среднюю схожесть за последние N сессий.
    Полезно для адаптивной настройки порога.
    """
    rows = get_recent_stats(n)
    if not rows:
        return None
    total_sim = sum(row[6] for row in rows if row[6] is not None)
    return total_sim / len(rows) if rows else None

def get_last_n_sent_count(n: int = 5):
    """
    Возвращает среднее количество отправленных новостей за последние N сессий.
    """
    rows = get_recent_stats(n)
    if not rows:
        return None
    total_sent = sum(row[3] for row in rows if row[3] is not None)
    return total_sent / len(rows) if rows else None
