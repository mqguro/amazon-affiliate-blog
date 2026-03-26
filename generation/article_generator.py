"""
Claude API-based article generation with template processing
"""

import anthropic
import json
from pathlib import Path
from storage.models import ProductData, ArticleData
from config.settings import Settings
from .affiliate import inject_affiliate_links
import logging

logger = logging.getLogger(__name__)


class ArticleGenerator:
    """Generate articles using Claude API"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.prompts_dir = Path(__file__).parent / "prompts"

        # Load products master
        products_file = Path(__file__).parent / "products_master.json"
        if products_file.exists():
            with open(products_file, 'r', encoding='utf-8') as f:
                self.products_master = json.load(f)
        else:
            self.products_master = {}

    def _get_master_products(self, category: str = None) -> dict:
        """Get product info from master data if available"""
        if not category or category not in self.products_master:
            return None
        return self.products_master[category]

    def _load_prompt_template(self, article_type: str, category: str = None) -> str:
        """Load prompt template for article type and category"""
        # Map article types to templates
        # "review" (3-product comparison) uses comparison template
        # "single_review" (1-product) uses review template
        if article_type == "single_review":
            template_type = "review"
        elif article_type == "review":
            template_type = "comparison"
        else:
            template_type = article_type

        # カテゴリ別テンプレートがあれば優先的に使用
        if category == "一人暮らし":
            template_file = self.prompts_dir / f"{template_type}_oneliving_ja.txt"
            if template_file.exists():
                return template_file.read_text(encoding="utf-8")

        # デフォルトテンプレート
        template_file = self.prompts_dir / f"{template_type}_ja.txt"

        if not template_file.exists():
            raise ValueError(f"Prompt template not found: {template_file}")

        return template_file.read_text(encoding="utf-8")

    def _prepare_prompt(
        self, article_type: str, products: list[ProductData], category: str = None
    ) -> tuple[str, str]:
        """
        Prepare system prompt and user message for Claude.
        Returns (system_prompt, user_message)
        """
        template = self._load_prompt_template(article_type, category)

        # Try to get products from master data
        product_info = self._get_master_products(category)

        if article_type == "review":
            # Review now generates 3-product comparison (cost/std/prem style)
            if not products or len(products) < 3:
                raise ValueError(
                    "Review article requires exactly 3 products (cost/std/prem)"
                )

            products_list = "\n".join(
                [
                    f"- {p.title} (¥{f'{p.price:,.0f}' if p.price else '情報なし'}) - "
                    f"評価: {p.rating if p.rating else '情報なし'}/5.0"
                    for p in products
                ]
            )

            # Get affiliate links for comparison
            cost_link = f"https://amzn.to/{products[0].url}" if products[0].url else products[0].asin
            std_link = f"https://amzn.to/{products[1].url}" if products[1].url else products[1].asin
            prem_link = f"https://amzn.to/{products[2].url}" if products[2].url else products[2].asin

            user_message = template.format(
                products_list=products_list,
                cost_link=cost_link,
                std_link=std_link,
                prem_link=prem_link,
            )

        elif article_type == "single_review":
            # Single product review
            if not products or len(products) != 1:
                raise ValueError(
                    "Single review article requires exactly 1 product"
                )

            product = products[0]

            # Use master data if available, otherwise use product data
            if product_info:
                title = product_info['cost']['name']
                cost_link = f"https://amzn.to/{product_info['cost']['url']}"
                std_title = product_info['std']['name']
                std_link = f"https://amzn.to/{product_info['std']['url']}"
                prem_title = product_info['prem']['name']
                prem_link = f"https://amzn.to/{product_info['prem']['url']}"

                user_message = template.format(
                    title=title,
                    cost_reason="コスパが優れている",
                    cost_user="予算を重視する人",
                    cost_caution="エントリー向けのため機能は限定的",
                    cost_price="3,000-5,000円帯が目安",
                    std_title=std_title,
                    std_reason="バランスが取れている",
                    std_user="標準的な用途向け",
                    std_caution="中級者向けの機能構成",
                    std_price="8,000-15,000円帯が目安",
                    prem_title=prem_title,
                    prem_reason="最高の性能を備えている",
                    prem_user="こだわりを求める人",
                    prem_caution="高い性能に見合う投資が必要",
                    prem_price="20,000円以上が目安",
                    cost_link=cost_link,
                    std_link=std_link,
                    prem_link=prem_link,
                )
            else:
                # Fallback to product data
                user_message = template.format(
                    title=product.title,
                    price=f"¥{product.price:,.0f}" if product.price else "情報なし",
                    rating=f"{product.rating:.1f}" if product.rating else "情報なし",
                    review_count=f"{product.review_count:,}"
                    if product.review_count
                    else "0",
                    asin=product.asin,
                )

        elif article_type == "comparison":
            if not products or len(products) < 3:
                raise ValueError(
                    "Comparison article requires exactly 3 products (cost/std/prem)"
                )

            products_list = "\n".join(
                [
                    f"- {p.title} (¥{f'{p.price:,.0f}' if p.price else '情報なし'}) - "
                    f"評価: {p.rating if p.rating else '情報なし'}/5.0"
                    for p in products
                ]
            )

            # Get affiliate links for comparison (build from products)
            cost_link = f"https://amzn.to/{products[0].url}" if products[0].url else products[0].asin
            std_link = f"https://amzn.to/{products[1].url}" if products[1].url else products[1].asin
            prem_link = f"https://amzn.to/{products[2].url}" if products[2].url else products[2].asin

            user_message = template.format(
                products_list=products_list,
                cost_link=cost_link,
                std_link=std_link,
                prem_link=prem_link,
            )

        elif article_type == "ranking":
            if not products:
                raise ValueError("Ranking article requires at least 1 product")

            products_list = "\n".join(
                [
                    f"{i+1}. {p.title} (¥{p.price:,.0f if p.price else '情報なし'}) - "
                    f"評価: {p.rating if p.rating else '情報なし'}/5.0 ({p.review_count if p.review_count else '0'}件)"
                    for i, p in enumerate(products)
                ]
            )
            user_message = template.format(products_list=products_list)

        else:
            raise ValueError(f"Unknown article type: {article_type}")

        system_prompt = (
            "あなたはプロのテクニカルライターです。"
            "指定された要件に従い、高品質な日本語記事を作成してください。"
        )

        return system_prompt, user_message

    def generate(
        self, article_type: str, products: list[ProductData], category: str = None
    ) -> ArticleData:
        """
        Generate an article using Claude API.

        Args:
            article_type: "review" (3-product comparison), "single_review", "comparison", or "ranking"
            products: List of ProductData objects
            category: Optional category for template selection

        Returns:
            ArticleData with generated content
        """

        logger.info(
            f"Generating {article_type} article for {len(products)} product(s) in {category}"
        )

        system_prompt, user_message = self._prepare_prompt(article_type, products, category)

        try:
            message = self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=self.settings.claude_max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            content = message.content[0].text

            # Extract title from first H1 heading
            title = "Untitled Article"
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            # Extract meta description (first paragraph after title)
            meta_description = ""
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("# ") and i + 1 < len(lines):
                    # Get next non-empty line
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip() and not lines[j].startswith("#"):
                            meta_description = lines[j][:160]
                            break
                    break

            # Inject affiliate links
            product_asins = [p.asin for p in products]
            content_with_links = inject_affiliate_links(
                content, product_asins, self.settings
            )

            # Count words (Japanese characters as words)
            word_count = len(content.replace("\n", "").replace(" ", ""))

            article = ArticleData(
                title=title,
                content=content_with_links,
                article_type=article_type,
                product_asins=product_asins,
                meta_description=meta_description,
                word_count=word_count,
            )

            logger.info(
                f"Generated article: '{title}' ({word_count} chars, {article_type})"
            )
            return article

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise

    def validate_article(self, article: ArticleData) -> bool:
        """Validate generated article meets requirements"""
        if not article.title or not article.content:
            logger.warning("Article missing title or content")
            return False

        if article.word_count < self.settings.min_word_count:
            logger.warning(
                f"Article too short: {article.word_count} < {self.settings.min_word_count}"
            )
            return False

        if not article.product_asins:
            logger.warning("Article has no associated products")
            return False

        return True
