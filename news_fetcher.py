import os
import requests
import feedparser
from datetime import datetime, timedelta, timezone

GNEWS_API_KEY = os.getenv('GNEWS_API_KEY')

def fetch_gnews(query='', max_articles=20):
    """Получает новости из GNews по ключевым словам."""
    if not GNEWS_API_KEY:
        return []
    from_date = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
    url = f"https://gnews.io/api/v4/search?q={query}&from={from_date}&max={max_articles}&apikey={GNEWS_API_KEY}&lang=ru"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"GNews ошибка: {resp.status_code}")
            return []
        data = resp.json()
        return data.get('articles', [])
    except Exception as e:
        print(f"❌ Ошибка GNews: {e}")
        return []

def fetch_rss_feeds(feeds, max_per_feed=5):
    """Парсит список RSS-лент."""
    all_articles = []
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                all_articles.append({
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'description': entry.get('summary', '') or entry.get('description', ''),
                    'publishedAt': entry.get('published', ''),
                    'source': {'name': feed.feed.get('title', 'Неизвестный источник')},
                    'image': ''
                })
        except Exception as e:
            print(f"❌ Ошибка парсинга RSS {feed_url}: {e}")
    return all_articles
