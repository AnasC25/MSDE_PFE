import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict
from playwright.async_api import async_playwright, Browser, Page
import boto3
from botocore.exceptions import ClientError

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration AWS
AWS_REGION = 'eu-west-3'
BUCKET_NAME = 'msde-pfe-scraping'
S3_PREFIX = 'cotepara'

class CoteParaScraper:
    def __init__(self):
        self.browser: Browser = None
        self.products: List[Dict] = []
        self.base_url = "https://cotepara.ma/best-sellers/1/"
        self.s3_client = boto3.client('s3', region_name=AWS_REGION)

    async def init_browser(self):
        """Initialize the browser."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)

    async def close_browser(self):
        """Close the browser."""
        if self.browser:
            await self.browser.close()

    def upload_to_s3(self, file_path: str) -> bool:
        """Upload a file to S3 bucket."""
        try:
            # Get the filename from the path
            filename = file_path.split('/')[-1]
            
            # Construct the S3 key
            s3_key = f"{S3_PREFIX}/{filename}"
            
            # Upload the file
            self.s3_client.upload_file(
                file_path,
                BUCKET_NAME,
                s3_key
            )
            
            logger.info(f"✅ Successfully uploaded to S3: s3://{BUCKET_NAME}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"❌ Error uploading to S3: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during S3 upload: {str(e)}")
            return False

    async def scrape_products(self):
        """Scrape products from the page."""
        try:
            page = await self.browser.new_page()
            await page.goto(self.base_url, wait_until='domcontentloaded')
            
            # Wait for products to load
            await page.wait_for_selector('.product-grid')
            
            # Get all products
            products = await page.query_selector_all('.product-grid .product-item')
            
            # Process each product
            for index, product in enumerate(products):
                try:
                    # Extract product data
                    title = await product.query_selector('.product-name')
                    price = await product.query_selector('.product-price')
                    old_price = await product.query_selector('.old-price')
                    
                    # Get text content
                    title_text = await title.text_content() if title else "N/A"
                    price_text = await price.text_content() if price else "N/A"
                    old_price_text = await old_price.text_content() if old_price else "N/A"
                    
                    # Calculate score (highest for first product, lowest for last)
                    score = len(products) - index
                    
                    # Add to products list
                    self.products.append({
                        "title": title_text.strip(),
                        "price": price_text.strip(),
                        "old_price": old_price_text.strip(),
                        "score": score
                    })
                    
                    logger.info(f"Scraped product: {title_text.strip()}")
                    
                except Exception as e:
                    logger.error(f"Error scraping product: {str(e)}")
                    continue
            
            # Save to JSON file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"cotepara_products_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.products, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ Successfully saved {len(self.products)} products to {filename}")
            
            # Upload to S3
            if self.upload_to_s3(filename):
                logger.info("✅ S3 upload completed successfully")
            else:
                logger.error("❌ S3 upload failed")
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
        finally:
            await page.close()

async def main():
    scraper = CoteParaScraper()
    try:
        await scraper.init_browser()
        await scraper.scrape_products()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        await scraper.close_browser()

if __name__ == "__main__":
    asyncio.run(main())
