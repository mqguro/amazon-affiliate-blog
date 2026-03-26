"""
Automatically find products on Amazon using Claude API
"""

import anthropic
from config.settings import Settings
import json
import logging

logger = logging.getLogger(__name__)


class ProductFinder:
    """Find products on Amazon using Claude"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def find_products(self, category: str) -> dict:
        """
        Find products for a category using Claude.

        Args:
            category: Product category name (e.g. "ゲーミングマウスパッド")

        Returns:
            dict with cost/std/prem products and their Amazon ASIN
        """

        logger.info(f"Finding products for category: {category}")

        prompt = f"""あなたは Amazon.co.jp で商品を探す専門家です。

以下のカテゴリについて、Amazon.co.jp で実際に売られている人気商品を探してください。

【カテゴリ】
{category}

【見つけるべき商品】
1. コスパ最強（安くて十分な性能）
2. 定番品（多くの人に選ばれている）
3. プレミアム（最高の性能・品質）

【出力形式】
JSON形式で、以下の構造で返してください：

```json
{{
  "cost": {{
    "name": "商品名（正確なAmazon掲載名）",
    "asin": "B0XXXXXXXX",
    "price": "価格の目安（例：3000-5000円）",
    "reason": "このカテゴリでコスパが最高の理由"
  }},
  "std": {{
    "name": "商品名",
    "asin": "B0XXXXXXXX",
    "price": "価格の目安",
    "reason": "このカテゴリの定番品の理由"
  }},
  "prem": {{
    "name": "商品名",
    "asin": "B0XXXXXXXX",
    "price": "価格の目安",
    "reason": "最高性能の理由"
  }}
}}
```

【重要】
- ASINは正確に（Bから始まる10文字）
- Amazon.co.jp で実際に検索すれば見つかる商品のみ
- 商品名は Amazon の掲載名をそのまま使う
- 虚偽・捏造は禁止

では、「{category}」について、実際の Amazon 商品情報を JSON で返してください。JSONのみ返す（説明文は不要）。
"""

        try:
            message = self.client.messages.create(
                model=self.settings.claude_model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            response_text = message.content[0].text

            # JSON を抽出
            try:
                # ```json ... ``` で囲まれている場合を処理
                if "```json" in response_text:
                    json_str = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    json_str = response_text.split("```")[1].split("```")[0].strip()
                else:
                    json_str = response_text.strip()

                result = json.loads(json_str)

                logger.info(f"Found products for {category}:")
                logger.info(f"  - Cost: {result['cost']['name']}")
                logger.info(f"  - Std: {result['std']['name']}")
                logger.info(f"  - Prem: {result['prem']['name']}")

                return result

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response: {response_text}")
                return None

        except Exception as e:
            logger.error(f"Product finder error: {e}")
            return None

    def find_and_cache(self, category: str) -> dict:
        """
        Find products and cache them in products_master.json
        """
        from pathlib import Path

        # First check if already cached
        master_file = Path(__file__).parent / "products_master.json"
        if master_file.exists():
            with open(master_file, 'r', encoding='utf-8') as f:
                master = json.load(f)
                if category in master:
                    logger.info(f"Using cached products for {category}")
                    return master[category]

        # Find products
        products = self.find_products(category)

        if not products:
            return None

        # Cache to products_master.json
        try:
            if master_file.exists():
                with open(master_file, 'r', encoding='utf-8') as f:
                    master = json.load(f)
            else:
                master = {}

            master[category] = products

            with open(master_file, 'w', encoding='utf-8') as f:
                json.dump(master, f, ensure_ascii=False, indent=2)

            logger.info(f"Cached products for {category}")

        except Exception as e:
            logger.error(f"Failed to cache products: {e}")

        return products
