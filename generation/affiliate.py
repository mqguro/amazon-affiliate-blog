"""
Amazon affiliate URL generation utility
"""

from config.settings import Settings
import logging

logger = logging.getLogger(__name__)


def build_affiliate_url(asin: str, settings: Settings) -> str:
    """
    Build Amazon.co.jp affiliate URL for a product.

    Format: https://www.amazon.co.jp/dp/{ASIN}/?tag={ASSOCIATE_ID}
    """
    return f"https://www.amazon.co.jp/dp/{asin}/?tag={settings.amazon_associate_id}"


def build_affiliate_link_html(asin: str, text: str, settings: Settings) -> str:
    """
    Build HTML anchor tag with affiliate link
    """
    url = build_affiliate_url(asin, settings)
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{text}</a>'


def build_markdown_affiliate_link(asin: str, text: str, settings: Settings) -> str:
    """
    Build Markdown affiliate link
    """
    url = build_affiliate_url(asin, settings)
    return f"[{text}]({url})"


def embed_product_image(image_url: str, alt_text: str = "Product") -> str:
    """
    Build HTML for product image embed
    """
    if not image_url:
        return ""
    return f'<img src="{image_url}" alt="{alt_text}" style="max-width: 100%; height: auto;">'


def embed_product_image_markdown(image_url: str, alt_text: str = "Product") -> str:
    """
    Build Markdown for product image
    """
    if not image_url:
        return ""
    return f"![{alt_text}]({image_url})"


def inject_affiliate_links(content: str, product_asins: list, settings: Settings) -> str:
    """
    Inject affiliate links into article content.
    Replaces [AFFILIATE_LINK_ASIN] placeholders with actual URLs.
    """
    result = content
    for asin in product_asins:
        placeholder = f"[AFFILIATE_LINK_{asin}]"
        url = build_affiliate_url(asin, settings)
        result = result.replace(placeholder, url)
    return result
