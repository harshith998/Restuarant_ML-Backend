"""Scraper configuration for Mimosas Southern Bar and Grill"""

# Restaurant details
RESTAURANT_NAME = "Mimosas Southern Bar and Grill"
RESTAURANT_LOCATION = "Myrtle Beach, SC"

# Yelp URL
YELP_URL = "https://www.yelp.com/biz/mimosas-myrtle-beach-2"

# Scraping settings
TARGET_REVIEW_COUNT = 75  # Number of reviews to scrape
OUTPUT_FILE = "output/reviews.json"

# Selenium settings
HEADLESS = False  # Set to True to run browser in background
TIMEOUT = 10  # Seconds to wait for elements
RETRY_ATTEMPTS = 3
PAGE_LOAD_DELAY = 3  # Seconds to wait after page load
SCROLL_DELAY = 2  # Seconds to wait after scrolling
