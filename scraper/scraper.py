"""
Yelp Review Scraper - Fixed Version
Uses flexible selectors that survive Yelp's frequent HTML changes
"""

import json
import hashlib
import time
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config import (
    YELP_URL,
    TARGET_REVIEW_COUNT,
    OUTPUT_FILE,
    HEADLESS,
    TIMEOUT,
    RESTAURANT_NAME,
    PAGE_LOAD_DELAY,
    SCROLL_DELAY
)

DEBUG = True  # Enable debug output


def setup_driver():
    """Initialize undetected Chrome driver to bypass bot detection"""
    options = uc.ChromeOptions()
    
    if HEADLESS:
        options.add_argument('--headless=new')
    
    # Basic options
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # Create undetected chrome driver
    driver = uc.Chrome(options=options, use_subprocess=True)
    
    return driver


def debug_print(msg):
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"[DEBUG] {msg}")


def generate_review_id(text: str, date: str) -> str:
    """Generate unique review identifier from text and date"""
    combined = f"{text[:50]}_{date}"
    return f"yelp_{hashlib.md5(combined.encode()).hexdigest()[:12]}"


def parse_relative_date(date_str: str) -> str:
    """Convert Yelp's relative dates to ISO 8601 format"""
    if not date_str:
        return datetime.now().isoformat() + 'Z'
    
    date_str = date_str.strip().lower()
    now = datetime.now()
    
    # Check for MM/DD/YYYY format
    date_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
    if date_match:
        try:
            parsed = datetime.strptime(f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}", '%m/%d/%Y')
            return parsed.isoformat() + 'Z'
        except ValueError:
            pass
    
    # Check for "Mon DD, YYYY" format (e.g., "Jan 15, 2024")
    month_match = re.search(r'([a-z]{3})\s+(\d{1,2}),?\s*(\d{4})', date_str)
    if month_match:
        try:
            parsed = datetime.strptime(f"{month_match.group(1)} {month_match.group(2)} {month_match.group(3)}", '%b %d %Y')
            return parsed.isoformat() + 'Z'
        except ValueError:
            pass
    
    # Parse relative dates
    if 'today' in date_str or 'just now' in date_str:
        return now.isoformat() + 'Z'
    
    if 'yesterday' in date_str:
        return (now - timedelta(days=1)).isoformat() + 'Z'
    
    # Extract number and unit for relative dates
    match = re.search(r'(\d+)\s*(day|week|month|year)s?\s*ago', date_str)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'day':
            delta = timedelta(days=num)
        elif unit == 'week':
            delta = timedelta(weeks=num)
        elif unit == 'month':
            delta = timedelta(days=num * 30)
        elif unit == 'year':
            delta = timedelta(days=num * 365)
        else:
            delta = timedelta(0)
        
        return (now - delta).isoformat() + 'Z'
    
    return now.isoformat() + 'Z'


def scroll_page(driver, scroll_count=5):
    """Scroll down to trigger lazy loading"""
    debug_print(f"Scrolling page {scroll_count} times...")
    
    for i in range(scroll_count):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_DELAY)
        debug_print(f"  Scroll {i+1}/{scroll_count}")
    
    # Scroll back to top
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)


def click_read_more_buttons(driver):
    """Click 'Read more' buttons to expand truncated reviews"""
    try:
        # Multiple possible selectors for read more buttons
        selectors = [
            "//button[contains(text(), 'Read more')]",
            "//a[contains(text(), 'Read more')]",
            "//span[contains(text(), 'Read more')]",
            "//*[contains(@class, 'read-more')]",
        ]
        
        for selector in selectors:
            buttons = driver.find_elements(By.XPATH, selector)
            debug_print(f"Found {len(buttons)} 'Read more' buttons with selector: {selector}")
            
            for btn in buttons[:20]:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.3)
                    btn.click()
                    time.sleep(0.5)
                except Exception:
                    continue
                    
    except Exception as e:
        debug_print(f"Note: Could not expand reviews: {e}")


def extract_reviews_with_beautifulsoup(driver):
    """
    Use BeautifulSoup for more flexible parsing.
    This is more resilient to Yelp's changing class names.
    """
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    reviews = []
    
    debug_print("Parsing with BeautifulSoup...")
    
    # Strategy 1: Find the reviews section by id
    reviews_section = soup.find('section', {'aria-label': 'Recommended Reviews'})
    if not reviews_section:
        reviews_section = soup.find('div', id='reviews')
    if not reviews_section:
        reviews_section = soup  # Fall back to whole page
    
    debug_print(f"Reviews section found: {reviews_section is not None}")
    
    # Strategy 2: Find review containers using partial class matching
    # Yelp reviews typically have comment/review in their class names
    review_containers = []
    
    # Try multiple strategies to find review elements
    strategies = [
        # Strategy A: Look for elements with 'review' in data attributes
        lambda: soup.find_all('li', attrs={'data-testid': lambda x: x and 'review' in x.lower()}) if soup.find_all('li', attrs={'data-testid': lambda x: x and 'review' in x.lower()}) else [],
        
        # Strategy B: Look for divs containing star ratings and text
        lambda: soup.find_all('div', class_=lambda x: x and any(c in str(x).lower() for c in ['review', 'comment'])),
        
        # Strategy C: Find by aria-label pattern
        lambda: soup.find_all(attrs={'aria-label': lambda x: x and 'star rating' in str(x).lower()}),
    ]
    
    for i, strategy in enumerate(strategies):
        try:
            found = strategy()
            debug_print(f"Strategy {i+1} found {len(found)} potential elements")
            if found:
                review_containers = found
                break
        except Exception as e:
            debug_print(f"Strategy {i+1} failed: {e}")
    
    # If we found rating elements, work backwards to find full review containers
    if review_containers and review_containers[0].name != 'li':
        debug_print("Trying to find parent review containers...")
        new_containers = []
        for elem in review_containers[:50]:
            # Go up to find a reasonable container
            parent = elem
            for _ in range(10):
                parent = parent.parent
                if parent is None:
                    break
                # Check if this parent contains review text (more than 50 chars)
                text = parent.get_text(strip=True)
                if len(text) > 100 and len(text) < 5000:
                    if parent not in new_containers:
                        new_containers.append(parent)
                    break
        review_containers = new_containers
        debug_print(f"Found {len(review_containers)} review containers via parent traversal")
    
    # Extract data from each review container
    for idx, container in enumerate(review_containers[:TARGET_REVIEW_COUNT]):
        try:
            review_data = extract_single_review(container, idx)
            if review_data and len(review_data.get('text', '')) > 20:
                reviews.append(review_data)
                debug_print(f"  Extracted review {len(reviews)}: {len(review_data['text'])} chars, {review_data['rating']} stars")
        except Exception as e:
            debug_print(f"  Failed to extract review {idx}: {e}")
    
    return reviews


def extract_single_review(container, idx):
    """Extract data from a single review container"""
    
    # Extract rating
    rating = 3  # default
    
    # Method 1: aria-label on rating element
    rating_elem = container.find(attrs={'aria-label': lambda x: x and 'star' in str(x).lower()})
    if rating_elem:
        aria = rating_elem.get('aria-label', '')
        match = re.search(r'(\d+)', aria)
        if match:
            rating = int(match.group(1))
    
    # Method 2: Count filled stars
    if rating == 3:
        stars = container.find_all(attrs={'aria-label': lambda x: x and 'star' in str(x).lower()})
        if stars:
            rating = len([s for s in stars if 'fill' in str(s).get('class', [])]) or 3
    
    # Extract text - use partial class matching
    text = ""
    
    # Method 1: Find spans/paragraphs with comment-like classes
    text_selectors = [
        container.find_all('span', class_=lambda x: x and 'raw' in str(x).lower()),
        container.find_all('p', class_=lambda x: x and 'comment' in str(x).lower()),
        container.find_all('span', class_=lambda x: x and 'comment' in str(x).lower()),
    ]
    
    for elements in text_selectors:
        for elem in elements:
            candidate = elem.get_text(strip=True)
            if len(candidate) > len(text) and len(candidate) > 20:
                text = candidate
    
    # Method 2: If no text found, get the longest paragraph
    if len(text) < 20:
        paragraphs = container.find_all(['p', 'span'])
        for p in paragraphs:
            candidate = p.get_text(strip=True)
            # Filter out navigation text, usernames, etc.
            if len(candidate) > len(text) and len(candidate) > 50:
                if not any(skip in candidate.lower() for skip in ['read more', 'useful', 'funny', 'cool', 'photo']):
                    text = candidate
    
    # Extract date
    date_str = ""
    
    # Method 1: Look for date patterns in text
    date_patterns = [
        r'\d{1,2}/\d{1,2}/\d{4}',
        r'[A-Z][a-z]{2}\s+\d{1,2},?\s*\d{4}',
        r'\d+\s*(day|week|month|year)s?\s*ago',
    ]
    
    all_text = container.get_text()
    for pattern in date_patterns:
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            date_str = match.group(0)
            break
    
    # Generate ID and return
    review_id = generate_review_id(text, date_str)
    
    return {
        "platform": "yelp",
        "review_identifier": review_id,
        "rating": rating,
        "text": text.strip(),
        "review_date": parse_relative_date(date_str)
    }


def extract_from_json_data(driver):
    """
    Try to extract review data from embedded JSON in the page.
    Yelp sometimes embeds data in script tags.
    """
    debug_print("Trying to extract from embedded JSON...")
    
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    reviews = []
    
    # Look for script tags with JSON data
    scripts = soup.find_all('script', type='application/json')
    scripts += soup.find_all('script', attrs={'data-hypernova-key': True})
    
    for script in scripts:
        try:
            data = json.loads(script.string)
            # Recursively search for review data
            found = find_reviews_in_json(data)
            if found:
                reviews.extend(found)
                debug_print(f"Found {len(found)} reviews in JSON data")
        except (json.JSONDecodeError, TypeError):
            continue
    
    return reviews


def find_reviews_in_json(obj, depth=0):
    """Recursively search for review data in nested JSON"""
    reviews = []
    
    if depth > 10:  # Prevent infinite recursion
        return reviews
    
    if isinstance(obj, dict):
        # Check if this dict looks like a review
        if 'text' in obj and 'rating' in obj:
            reviews.append({
                "platform": "yelp",
                "review_identifier": generate_review_id(
                    obj.get('text', '')[:50],
                    obj.get('date', obj.get('time_created', ''))
                ),
                "rating": obj.get('rating', 3),
                "text": obj.get('text', obj.get('comment', '')),
                "review_date": parse_relative_date(obj.get('date', obj.get('time_created', '')))
            })
        
        # Continue searching
        for key, value in obj.items():
            if key.lower() in ['reviews', 'review', 'comments']:
                reviews.extend(find_reviews_in_json(value, depth + 1))
            elif isinstance(value, (dict, list)):
                reviews.extend(find_reviews_in_json(value, depth + 1))
    
    elif isinstance(obj, list):
        for item in obj:
            reviews.extend(find_reviews_in_json(item, depth + 1))
    
    return reviews


def navigate_pagination(driver, current_page, max_pages=5):
    """Handle pagination to get more reviews"""
    debug_print(f"Attempting to navigate to page {current_page + 1}...")
    
    try:
        # Look for pagination links
        pagination_selectors = [
            f"//a[contains(@href, 'start={current_page * 10}')]",
            "//a[contains(@class, 'next')]",
            "//a[contains(@aria-label, 'Next')]",
            "//button[contains(text(), 'Next')]",
        ]
        
        for selector in pagination_selectors:
            try:
                next_btn = driver.find_element(By.XPATH, selector)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                time.sleep(1)
                next_btn.click()
                time.sleep(PAGE_LOAD_DELAY)
                return True
            except NoSuchElementException:
                continue
        
        # Alternative: modify URL directly
        current_url = driver.current_url
        if 'start=' in current_url:
            new_url = re.sub(r'start=\d+', f'start={current_page * 10}', current_url)
        else:
            separator = '&' if '?' in current_url else '?'
            new_url = f"{current_url}{separator}start={current_page * 10}"
        
        driver.get(new_url)
        time.sleep(PAGE_LOAD_DELAY)
        return True
        
    except Exception as e:
        debug_print(f"Pagination failed: {e}")
        return False


def save_debug_screenshot(driver, name="debug"):
    """Save a screenshot for debugging"""
    if DEBUG:
        filename = f"{name}_{int(time.time())}.png"
        driver.save_screenshot(filename)
        debug_print(f"Screenshot saved: {filename}")


def scrape_yelp_reviews(driver):
    """Main scraping function"""
    print(f"\n{'='*60}")
    print(f"  Yelp Review Scraper - Fixed Version")
    print(f"  Restaurant: {RESTAURANT_NAME}")
    print(f"  Target: {TARGET_REVIEW_COUNT} reviews")
    print(f"{'='*60}\n")
    
    all_reviews = []
    
    print(f"Loading: {YELP_URL}")
    driver.get(YELP_URL)
    time.sleep(PAGE_LOAD_DELAY)
    
    # Save debug screenshot
    save_debug_screenshot(driver, "initial_load")
    
    # Check for CAPTCHA or block - be more specific
    page_text = driver.page_source.lower()
    page_title = driver.title.lower()
    
    # More accurate CAPTCHA detection - check for actual CAPTCHA elements
    is_captcha = False
    captcha_indicators = [
        'please verify you are a human',
        'unusual traffic',
        'press & hold',
        'verify you are human',
        'robot check',
        'are you a human',
        'captcha-delivery',
    ]
    
    for indicator in captcha_indicators:
        if indicator in page_text:
            is_captcha = True
            debug_print(f"CAPTCHA indicator found: '{indicator}'")
            break
    
    # Also check if we're NOT on a Yelp business page
    if 'yelp' not in page_title and 'mimosas' not in page_title:
        is_captcha = True
        debug_print(f"Page title doesn't look right: {driver.title}")
    
    if is_captcha:
        print("\n⚠️  CAPTCHA or bot detection may have been triggered!")
        print("    Page title:", driver.title)
        
        if not HEADLESS:
            print("\n🔧 MANUAL INTERVENTION MODE")
            print("   The browser window is open. If you see a CAPTCHA:")
            print("   1. Solve it manually in the browser window")
            print("   2. Wait for the page to load")
            print("   3. Press ENTER here to continue...")
            input("\n   Press ENTER when ready to continue (or Ctrl+C to abort): ")
            time.sleep(2)
            # Re-check after manual intervention
            page_text = driver.page_source.lower()
        else:
            print("    Set HEADLESS = False in config.py to solve manually")
            save_debug_screenshot(driver, "captcha_detected")
            return []
    
    # Verify we're on the right page by checking for review-related content
    if 'review' not in page_text and 'rating' not in page_text:
        print("\n⚠️  Page doesn't appear to contain reviews")
        print(f"    Title: {driver.title}")
        save_debug_screenshot(driver, "no_reviews_found")
        
        if not HEADLESS:
            print("\n   Check the browser window. Press ENTER to try extracting anyway...")
            input()
    
    debug_print(f"Page title: {driver.title}")
    
    # Scroll to load lazy content
    scroll_page(driver, scroll_count=3)
    
    # Expand truncated reviews
    click_read_more_buttons(driver)
    
    # Try multiple extraction methods
    print("\nExtracting reviews...")
    
    # Method 1: BeautifulSoup parsing
    reviews = extract_reviews_with_beautifulsoup(driver)
    all_reviews.extend(reviews)
    print(f"  Method 1 (BeautifulSoup): {len(reviews)} reviews")
    
    # Method 2: Embedded JSON
    if len(all_reviews) < TARGET_REVIEW_COUNT:
        json_reviews = extract_from_json_data(driver)
        # Deduplicate by review_identifier
        existing_ids = {r['review_identifier'] for r in all_reviews}
        new_reviews = [r for r in json_reviews if r['review_identifier'] not in existing_ids]
        all_reviews.extend(new_reviews)
        print(f"  Method 2 (JSON): {len(new_reviews)} additional reviews")
    
    # Pagination if needed
    page = 1
    max_pages = 5
    while len(all_reviews) < TARGET_REVIEW_COUNT and page < max_pages:
        print(f"\n  Trying page {page + 1}...")
        if navigate_pagination(driver, page):
            time.sleep(PAGE_LOAD_DELAY)
            
            page_reviews = extract_reviews_with_beautifulsoup(driver)
            existing_ids = {r['review_identifier'] for r in all_reviews}
            new_reviews = [r for r in page_reviews if r['review_identifier'] not in existing_ids]
            all_reviews.extend(new_reviews)
            print(f"    Found {len(new_reviews)} new reviews on page {page + 1}")
            
            page += 1
        else:
            break
    
    # Deduplicate final list
    seen = set()
    unique_reviews = []
    for review in all_reviews:
        if review['review_identifier'] not in seen and len(review['text']) > 20:
            seen.add(review['review_identifier'])
            unique_reviews.append(review)
    
    return unique_reviews[:TARGET_REVIEW_COUNT]


def save_reviews(reviews, output_path):
    """Save reviews to JSON file"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Saved {len(reviews)} reviews to {output_path}")


def main():
    """Main entry point"""
    driver = setup_driver()
    
    try:
        reviews = scrape_yelp_reviews(driver)
        
        if reviews:
            save_reviews(reviews, OUTPUT_FILE)
            
            print(f"\n{'='*60}")
            print(f"✅ SUCCESS!")
            print(f"   Total reviews: {len(reviews)}")
            print(f"   Output file: {OUTPUT_FILE}")
            print(f"{'='*60}")
            
            # Print sample
            if reviews:
                print(f"\n📝 Sample review:")
                sample = reviews[0]
                print(f"   Rating: {'⭐' * sample['rating']}")
                print(f"   Text: {sample['text'][:150]}...")
        else:
            print("\n❌ No reviews were scraped")
            print("\nTroubleshooting tips:")
            print("  1. Set HEADLESS = False to see what's happening")
            print("  2. Check if the URL is correct")
            print("  3. Yelp may have changed their HTML structure")
            print("  4. Try waiting longer (increase PAGE_LOAD_DELAY)")
            print("  5. Consider using a proxy or VPN")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        save_debug_screenshot(driver, "error")
        
    finally:
        print("\nClosing browser...")
        try:
            driver.quit()
        except OSError:
            pass  # Ignore Windows handle errors on quit


if __name__ == "__main__":
    main()
    