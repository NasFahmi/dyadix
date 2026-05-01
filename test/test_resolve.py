import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

def resolve_gnews_link():
    url = "https://news.google.com/rss/search?q=bitcoin+site:finance.yahoo.com&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            content = response.read()
            
        root = ET.fromstring(content)
        channel = root.find("channel")
        items = channel.findall("item")
        if not items:
            print("No items")
            return
            
        gnews_link = items[0].find("link").text
        print(f"Google News Link: {gnews_link}")
        
        # Resolve the redirect
        req_redirect = urllib.request.Request(gnews_link, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_redirect) as response:
            resolved_url = response.geturl()
            print(f"Resolved URL: {resolved_url}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    resolve_gnews_link()
