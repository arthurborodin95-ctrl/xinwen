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

    # ---- ФИЛЬТР ПО ВРЕМЕНИ (только свежие новости) ----
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
                # Если дата не парсится, пропускаем статью
                pass
    all_articles = filtered_by_time
    print(f"После фильтрации по времени (последние {MAX_HOURS_OLD} ч.) осталось {len(all_articles)} статей.")
    print(f"Всего собрано {len(all_articles)} статей из RSS (с учётом времени).")
    return all_articles