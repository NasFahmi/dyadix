import feedparser

xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<item>
<title>
<![CDATA[ MARA Holdings to buy Long Ridge Energy in $1.5 billion AI data center push ]]>
</title>
<link>https://www.coindesk.com/business/2026/04/30/mara-holdings-to-buy-long-ridge-energy-in-usd1-5-billion-ai-data-center-push</link>
<description>
<![CDATA[ The deal includes a 505 MW gas plant and 1,600 acres in Ohio, offering over 1 GW power capacity for future AI and IT buildout. ]]>
</description>
<dc:creator>Francisco Rodrigues</dc:creator>
<content:encoded/>
<dc:description/>
</item>
</channel>
</rss>
"""

feed = feedparser.parse(xml_data)
entry = feed.entries[0]

print("Keys:", entry.keys())
print("summary:", entry.get('summary'))
print("description:", entry.get('description'))
print("dc:description (often stored differently):", entry.get('dc_description', getattr(entry, 'dc_description', None)))

