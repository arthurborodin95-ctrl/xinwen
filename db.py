import sqlite3

DB_FILE = 'news.db'

def init_db():
    """Создаёт таблицу и индексы при первом запуске."""
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
    conn.commit()
    conn.close()

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
    """Удаляет статьи старше указанного количества дней (экономия места)."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM sent_articles WHERE sent_at < datetime("now", ?)',
        (f'-{days} days',)
    )
    conn.commit()
    conn.close()
