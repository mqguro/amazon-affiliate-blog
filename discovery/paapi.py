"""
Amazon PA-API v5 wrapper for product discovery (primary method)
Falls back to scraper if credentials not configured.
"""

from storage.models import ProductData
from config.settings import Settings
from typing import List
import logging
import time

logger = logging.getLogger(__name__)


class PAAPIClient:
    """Amazon Product Advertising API v5 client"""

    def __init__(self, settings: Settings):
        self.settings = settings

        if not settings.has_paapi_credentials:
            logger.warning(
                "PA-API credentials not configured. "
                "Using BeautifulSoup scraper fallback instead."
            )
            self._paapi = None
            return

        try:
            from paapi5_python_sdk.api.default_api import DefaultApi
            from paapi5_python_sdk.models.search_items_request import SearchItemsRequest
            from paapi5_python_sdk.rest import ApiException

            self.DefaultApi = DefaultApi
            self.SearchItemsRequest = SearchItemsRequest
            self.ApiException = ApiException

            # Initialize API client
            self.client = DefaultApi()
            self.client.api_key = settings.paapi_access_key
            self.client.api_secret = settings.paapi_secret_key
            self.client.host = "webservices.amazon.co.jp"
            self.client.region = "ap_northeast_1"

            self._paapi = True
            logger.info("PA-API v5 client initialized successfully")

        except ImportError:
            logger.warning(
                "paapi5-python-sdk not installed. "
                "Install with: pip install paapi5-python-sdk"
            )
            self._paapi = None

    def search(
        self, keyword: str, category: str = None, limit: int = 5
    ) -> List[ProductData]:
        """
        Search for products using PA-API.
        Falls back to scraper if PA-API unavailable.
        """

        if not self._paapi:
            logger.debug(f"PA-API disabled, using scraper for: {keyword}")
            from .scraper import AmazonScraper

            scraper = AmazonScraper(self.settings)
            products = scraper.search(keyword, category, limit)
            scraper.close()
            return products

        try:
            logger.info(f"Searching PA-API for keyword: {keyword}")

            request = self.SearchItemsRequest(
                keywords=keyword,
                partner_tag=self.settings.paapi_partner_tag,
                search_index="All",
                item_count=limit,
                resources=[
                    "ItemInfo.Title",
                    "ItemInfo.ByLineInfo",
                    "Images.Primary.Large",
                    "ItemInfo.Features",
                    "Offers.Listings.Price",
                    "ItemInfo.Classifications",
                    "CustomerReviews.Count",
                    "CustomerReviews.StarRating",
                    "Images.Variants",
                ],
            )

            response = self.client.search_items(request)

            products = []
            if response.search_result and response.search_result.items:
                for item in response.search_result.items[:limit]:
                    try:
                        asin = item.asin
                        title = (
                            item.item_info.title.display_value
                            if item.item_info and item.item_info.title
                            else f"Product {asin}"
                        )

                        # Price
                        price = None
                        if (
                            item.offers
                            and item.offers.listings
                            and len(item.offers.listings) > 0
                        ):
                            listing = item.offers.listings[0]
                            if listing.price and listing.price.display_value:
                                price_str = listing.price.display_value.replace(
                                    "¥", ""
                                ).replace(",", "")
                                try:
                                    price = float(price_str)
                                except ValueError:
                                    pass

                        # Rating and review count
                        rating = None
                        review_count = None
                        if item.customer_reviews:
                            rating = item.customer_reviews.star_rating
                            review_count = item.customer_reviews.count

                        # Image URL
                        image_url = None
                        if (
                            item.images
                            and item.images.primary
                            and item.images.primary.large
                        ):
                            image_url = item.images.primary.large.url

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
                        logger.debug(f"PA-API product: {asin} - {title}")

                    except Exception as e:
                        logger.error(f"Error parsing PA-API item: {e}")
                        continue

            # Respect PA-API rate limit (1 request per second)
            time.sleep(1.0 / self.settings.paapi_requests_per_second)
            return products

        except Exception as e:
            logger.error(f"PA-API error: {e}. Falling back to scraper.")
            from .scraper import AmazonScraper

            scraper = AmazonScraper(self.settings)
            products = scraper.search(keyword, category, limit)
            scraper.close()
            return products
