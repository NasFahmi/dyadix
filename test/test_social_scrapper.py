import logging
import sys
import os

# Menambahkan root project ke sys.path agar bisa import module
sys.path.append(os.getcwd())

from service.sentiment.news.social_scrapper import SocialScrapper

# Setup logging ke console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Fix encoding untuk terminal Windows agar bisa print emoji
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def test_scrape():
    print("=== Testing SocialScrapper (Detailed with Comments) ===")
    scrapper = SocialScrapper()
    
    # Kita tes hanya 1 subreddit agar tidak terlalu lama (karena fetch comments butuh request extra)
    test_subs = ["CryptoCurrency"]
    results = scrapper.scrape(
        subreddits=test_subs, 
        limit_per_subreddit=2, 
        include_comments=True,
        comments_limit=2
    )
    
    for sub, posts in results.items():
        print(f"\nSubreddit: r/{sub}")
        if not posts:
            print("  [!] No posts found or error occurred.")
        for i, post in enumerate(posts, 1):
            print(f"  {i}. {post['title']}")
            if post['description']:
                print(f"     Description: {post['description']}")
            else:
                print("     Description: (No text content)")
                
            print(f"     URL: {post['url']}")
            print(f"     Score: {post['score']} | Comments Count: {post['num_comments']}")
            
            if "comments" in post and post["comments"]:
                print("     Top Comments:")
                for j, comment in enumerate(post["comments"], 1):
                    clean_comment = comment.replace("\n", " ")[:150]
                    print(f"       - {clean_comment}")
            else:
                print("     Top Comments: (No comments fetched)")

if __name__ == "__main__":
    test_scrape()
