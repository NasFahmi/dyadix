import requests
import feedparser

def test_google_news():
    url = "https://news.google.com/rss/search?q=bitcoin+site:finance.yahoo.com&hl=en-US&gl=US&ceid=US:en"
    response = requests.get(url)
    print(response.status_code)
    feed = feedparser.parse(response.content)
    print(f"Got {len(feed.entries)} entries")
    for entry in feed.entries[:3]:
        print(entry.title)
        print(entry.link)
        print(entry.published)

if __name__ == "__main__":
    test_google_news()
