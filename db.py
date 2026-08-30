import sqlite3
import json

DB_FILE = 'news.db'

def init_db():
    """Создаёт все таблицы и индексы при первом запуске."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # ---- Таблица отправленных статей (с полем hash) ----
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            source TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            hash TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_url ON sent_articles (url)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_title ON sent_articles (title)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_articles (sent_at)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON sent_articles (hash)')

    # ---- Таблица кэша эмбеддингов (если используется) ----
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS article_embeddings (
            hash TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON article_embeddings (created_at)')

    # ---- Таблица эталонных векторов (если используется) ----
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topic_embeddings (
            group_name TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ---- Таблица статистики сессий ----
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
            extra_data TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON session_stats (timestamp)')

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована (с поддержкой хешей).")

# ============================================================
# ФУНКЦИИ ДЕДУПЛИКАЦИИ ПО ХЕШУ
# ============================================================

def is_hash_sent_today(hash_value: str) -> bool:
    """
    Проверяет, был ли уже сегодня отправлен хеш (заголовок + описание).
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT 1 FROM sent_articles WHERE hash = ? AND date(sent_at) = date("now")',
        (hash_value,)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def mark_article_sent(url: str, title: str, source: str = '', hash_value: str = ''):
    """Сохраняет отправленную статью с хешем."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO sent_articles (url, title, source, hash) VALUES (?, ?, ?, ?)',
        (url, title, source, hash_value)
    )
    conn.commit()
    conn.close()

def get_total_sent() -> int:
    """Возвращает общее количество отправленных статей (за всё время)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sent_articles')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def clear_old_entries(days: int = 7):
    """Удаляет записи старше указанного количества дней (для экономии места)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM sent_articles WHERE sent_at < datetime("now", ?)',
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()

# ============================================================
# ФУНКЦИИ ДЛЯ ЭМБЕДДИНГОВ (если используются)
# ============================================================

def get_embedding(text_hash: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT embedding FROM article_embeddings WHERE hash = ?', (text_hash,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def save_embedding(text_hash: str, embedding: list):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO article_embeddings (hash, embedding) VALUES (?, ?)',
        (text_hash, json.dumps(embedding))
    )
    conn.commit()
    conn.close()

def get_all_topic_embeddings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT group_name, embedding FROM topic_embeddings')
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for name, emb_json in rows:
        result[name] = json.loads(emb_json)
    return result

def save_topic_embedding(group_name: str, embedding: list):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO topic_embeddings (group_name, embedding) VALUES (?, ?)',
        (group_name, json.dumps(embedding))
    )
    conn.commit()
    conn.close()

def clear_topic_embeddings():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM topic_embeddings')
    conn.commit()
    conn.close()

# ============================================================
# СТАТИСТИКА СЕССИЙ
# ============================================================

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