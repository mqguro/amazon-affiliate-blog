"""
BeautifulSoup-based Amazon.co.jp web scraper (fallback for PA-API)
"""

import time
import requests
from bs4 import BeautifulSoup
from storage.models import ProductData
from config.settings import Settings
from typing import List
import logging

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
]


class AmazonScraper:
    """Amazon.co.jp web scraper using BeautifulSoup"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENTS[0],
                "Accept-Language": "ja-JP,ja;q=0.9",
            }
        )

    def search(self, keyword: str, category: str = None, limit: int = 5) -> List[ProductData]:
        """
        Search Amazon.co.jp for products matching keyword.
        Returns list of ProductData objects.
        """
        logger.info(f"Scraping Amazon for keyword: {keyword}")

        products = []
        base_url = f"https://www.amazon.co.jp/s?k={keyword}"

        try:
            # Rotate user agent
            self.session.headers[
                "User-Agent"
            ] = USER_AGENTS[len(products) % len(USER_AGENTS)]

            response = self.session.get(base_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "lxml")

            # Amazon search results container
            result_items = soup.find_all(
                "div", {"data-component-type": "s-search-result"}
            )

            for item in result_items[:limit]:
                try:
                    # Extract ASIN from data attribute
                    asin = item.get("data-asin")
                    if not asin:
                        continue

                    # Title
                    title_elem = item.find("h2", {"class": "s-size-mini"})
                    title = (
                        title_elem.get_text(strip=True)
                        if title_elem
                        else f"Product {asin}"
                    )

                    # Price
                    price = None
                    price_elem = item.find("span", {"class": "a-price-whole"})
                    if price_elem:
                        price_text = price_elem.get_text(strip=True).replace("¥", "").replace(",", "")
                        try:
                            price = float(price_text)
                        except ValueError:
                            pass

                    # Rating
                    rating = None
                    rating_elem = item.find("span", {"class": "a-icon-star-small"})
                    if rating_elem:
                        rating_text = rating_elem.get_text(strip=True).split()[0]
                        try:
                            rating = float(rating_text)
                        except ValueError:
                            pass

                    # Review count
                    review_count = None
                    review_elem = item.find("span", {"class": "a-size-base"})
                    if review_elem:
                        review_text = review_elem.get_text(strip=True).replace(",", "")
                        try:
                            review_count = int(review_text)
                        except ValueError:
                            pass

                    # Image URL
                    image_url = None
                    img_elem = item.find("img", {"class": "s-image"})
                    if img_elem and img_elem.get("src"):
                        image_url = img_elem.get("src")

                    # Amazon product URL
                    url = f"https://www.amazon.co.jp/dp/{asin}/"

                    product = ProductData(
                        asin=asin,
                        title=title,
                        url=url,
                        category=category or self.settings.default_category,
                        price=price,
                        rating=rating,
                        review_count=review_count,
                        image_url=image_url,
                    )
                    products.append(product)
                    logger.debug(f"Scraped product: {asin} - {title}")

                except Exception as e:
                    logger.error(f"Error parsing product item: {e}")
                    continue

            # Polite delay before returning
            time.sleep(self.settings.scraper_delay_seconds)

        except requests.exceptions.RequestException as e:
            logger.error(f"Error scraping Amazon: {e}")

        return products

    def close(self):
        """Close the session"""
        self.session.close()
