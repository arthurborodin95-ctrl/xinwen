import sqlite3
import json

DB_FILE = 'news.db'

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

def init_db():
    """Создаёт все необходимые таблицы и индексы при первом запуске."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS article_embeddings (
            hash TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON article_embeddings (created_at)')

    # Таблица для эталонных векторов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS topic_embeddings (
            group_name TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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
    print("✅ База данных инициализирована.")


# ==================== ОТПРАВЛЕННЫЕ СТАТЬИ ====================

def is_article_sent(url: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM sent_articles WHERE url = ?', (url,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def mark_article_sent(url: str, title: str, source: str = ''):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR IGNORE INTO sent_articles (url, title, source) VALUES (?, ?, ?)',
        (url, title, source)
    )
    conn.commit()
    conn.close()

def get_total_sent() -> int:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sent_articles')
    count = cursor.fetchone()[0]
    conn.close()
    return count

def clear_old_entries(days: int = 30):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM sent_articles WHERE sent_at < datetime("now", ?)',
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()


# ==================== КЭШ ЭМБЕДДИНГОВ СТАТЕЙ ====================

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

def clear_old_embeddings(days: int = 30):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM article_embeddings WHERE created_at < datetime("now", ?)',
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()


# ==================== ЭТАЛОННЫЕ ВЕКТОРЫ (ТЕМАТИЧЕСКИЕ ГРУППЫ) ====================

def get_topic_embedding(group_name: str):
    """Возвращает сохранённый эталонный вектор для группы."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT embedding FROM topic_embeddings WHERE group_name = ?', (group_name,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None

def save_topic_embedding(group_name: str, embedding: list):
    """Сохраняет эталонный вектор для группы."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO topic_embeddings (group_name, embedding) VALUES (?, ?)',
        (group_name, json.dumps(embedding))
    )
    conn.commit()
    conn.close()

def get_all_topic_embeddings():
    """Возвращает все сохранённые эталонные векторы (словарь group_name -> embedding)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT group_name, embedding FROM topic_embeddings')
    rows = cursor.fetchall()
    conn.close()
    result = {}
    for name, emb_json in rows:
        result[name] = json.loads(emb_json)
    return result

def clear_topic_embeddings():
    """Удаляет все эталонные векторы (если нужно пересчитать)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM topic_embeddings')
    conn.commit()
    conn.close()


# ==================== СТАТИСТИКА СЕССИЙ ====================

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

def get_recent_stats(limit: int = 10):
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
    rows = get_recent_stats(n)
    if not rows:
        return None
    total_sim = sum(row[6] for row in rows if row[6] is not None)
    return total_sim / len(rows) if rows else None

def get_last_n_sent_count(n: int = 5):
    rows = get_recent_stats(n)
    if not rows:
        return None
    total_sent = sum(row[3] for row in rows if row[3] is not None)
    return total_sent / len(rows) if rows else None
