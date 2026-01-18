# Yelp Review Scraper

Scrapes reviews from Yelp for **Mimosas Southern Bar and Grill** in Myrtle Beach.

## Setup

```bash
cd scraper
pip install -r requirements.txt
```

This will install:
- `selenium` - Browser automation
- `webdriver-manager` - Automatic ChromeDriver management

## Usage

```bash
python scraper.py
```

Output: `output/reviews.json`

## Configuration

Edit `config.py` to change:
- `TARGET_REVIEW_COUNT` - Number of reviews to scrape (default: 75)
- `OUTPUT_FILE` - Output file path
- `HEADLESS` - Run browser in background (default: False for debugging)
- `TIMEOUT` - Seconds to wait for elements (default: 10)
- `PAGE_LOAD_DELAY` - Delay after page load (default: 3s)
- `SCROLL_DELAY` - Delay between scrolls (default: 2s)

## Output Format

JSON array with reviews:

```json
[
  {
    "platform": "yelp",
    "review_identifier": "yelp_a1b2c3d4e5f6",
    "rating": 5,
    "text": "Amazing southern food! The shrimp and grits were incredible...",
    "review_date": "2024-01-15T00:00:00Z"
  },
  {
    "platform": "yelp",
    "review_identifier": "yelp_f6e5d4c3b2a1",
    "rating": 2,
    "text": "Service was extremely slow. Waited 45 minutes...",
    "review_date": "2024-01-10T00:00:00Z"
  }
]
```

## How It Works

1. **Browser Setup** - Initializes Chrome with anti-detection settings
2. **Page Load** - Navigates to Yelp business page
3. **Scroll Loading** - Scrolls to trigger lazy-loaded reviews
4. **Expand Reviews** - Clicks "Read more" buttons to get full text
5. **Extract Data** - Parses rating, text, and date from each review
6. **Save JSON** - Outputs to `output/reviews.json`

## Features

- **Anti-Bot Measures**: User-agent spoofing, automation flag removal
- **Date Parsing**: Converts relative dates ("3 days ago") to ISO 8601
- **Error Handling**: Gracefully handles missing elements
- **Unique IDs**: Generates unique identifiers per review
- **Progress Tracking**: Console output shows scraping progress

## Troubleshooting

**No reviews found:**
- Check if Yelp page structure changed
- Verify the YELP_URL is correct
- Try running with `HEADLESS = False` to see browser

**Timeout errors:**
- Increase `TIMEOUT` and `PAGE_LOAD_DELAY` in config.py
- Check your internet connection

**CAPTCHA detected:**
- Yelp may show CAPTCHA for automated access
- Try increasing delays between requests
- Run scraper during off-peak hours
- Consider manual CAPTCHA solving if needed

## Notes

- Scraper respects Yelp's content by adding delays
- Reviews are for legitimate business analysis purposes
- Check Yelp's Terms of Service for compliance
