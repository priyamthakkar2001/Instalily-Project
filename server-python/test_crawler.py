import os
import asyncio
import json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
import re

def find_most_relevant_filter(products):
    """Find the most relevant water filter from the list of products."""
    # Score each product based on relevance
    max_score = 0
    best_product = None
    
    for product in products:
        score = 0
        content = product.get('content', [])
        name = content[0].lower() if content else ''
        
        # Check if it's a water filter
        if 'water filter' in name:
            score += 5
        elif 'filter' in name:
            score += 2
            
        # Check if it's an actual filter vs accessories
        if any(x in name.lower() for x in ['base', 'housing', 'cap', 'mount']):
            score -= 3
            
        # Prefer items with more complete information
        score += len(content)
        
        if score > max_score:
            max_score = score
            best_product = product
            
    return best_product

def construct_product_url(part_number, manufacturer_number, name, model):
    """Construct the complete product URL with SEO-friendly format."""
    # Remove "PartSelect #: " and "Manufacturer #: " prefixes
    part_number = part_number.split('#: ')[1].strip() if '#: ' in part_number else part_number
    manufacturer_number = manufacturer_number.split('#: ')[1].strip() if '#: ' in manufacturer_number else manufacturer_number
    
    # Clean the product name for URL
    name = name.replace('Refrigerator ', '')  # Remove common prefixes
    name = re.sub(r'[^\w\s-]', '', name)  # Remove special characters
    name = name.replace(' ', '-')  # Replace spaces with hyphens
    
    # Construct URL in the format: PS<number>-Brand-MfrNumber-Product-Name.htm
    url = f"https://www.partselect.com/{part_number}-Frigidaire-{manufacturer_number}-{name}.htm"
    url += f"?SourceCode=21&SearchTerm={model}&ModelNum={model}"
    
    return url

async def test_crawler():
    # Initialize crawler with configuration
    browser_cfg = BrowserConfig(
        headless=True,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    )
    
    # Define the LLM extraction strategy
    llm_strategy = LLMExtractionStrategy(
        api_token=os.getenv("OPENAI_API_KEY"),
        provider="openai/gpt-4",
        extraction_type="block",
        instruction="""Find water filter products and related items for this refrigerator model. For each product found, extract in order:
        1. Product name
        2. PartSelect number
        3. Manufacturer number
        4. Description
        5. Location information
        6. Any discount information
        7. Current price
        8. Original price (if discounted)
        9. Product URL
        
        Format the response as a JSON array of objects with 'index', 'tag', and 'content' fields, where content is an array of the above information in order.""",
        chunk_token_threshold=800,
        overlap_rate=0.1,
        apply_chunking=True,
        input_format="markdown",
        extra_args={"temperature": 0.0, "max_tokens": 1000},
        verbose=True,
    )
    
    # Configure the crawler
    crawl_config = CrawlerRunConfig(
        extraction_strategy=llm_strategy,
        cache_mode=CacheMode.BYPASS,
        process_iframes=False,
        remove_overlay_elements=True,
        excluded_tags=["form", "header", "footer"],
    )
    
    # URL to test
    model = "LFSS2612TF0"
    url = f"https://www.partselect.com/Models/{model}/Parts/?SearchTerm=water%20filter"
    
    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            # Crawl the URL
            result = await crawler.arun(url=url, config=crawl_config)
            
            if result.success:
                try:
                    # Parse the JSON response
                    products = json.loads(result.extracted_content)
                    
                    # Find the most relevant water filter
                    best_product = find_most_relevant_filter(products)
                    
                    if best_product:
                        content = best_product['content']
                        print(f"\nMost Relevant Water Filter for {model}:")
                        print(f"Name: {content[0]}")
                        print(f"Part Number: {content[1]}")
                        print(f"Manufacturer Number: {content[2]}")
                        if len(content) > 3:
                            print(f"Description: {content[3]}")
                        
                        # Print pricing information
                        price_info = [x for x in content if '$' in x]
                        if price_info:
                            print(f"Price: {price_info[0]}")
                        
                        # Construct and print the complete product URL
                        product_url = construct_product_url(content[1], content[2], content[0], model)
                        print(f"Product URL: {product_url}")
                    else:
                        print("No relevant water filter found.")
                    
                except json.JSONDecodeError as e:
                    print("Raw extracted content:")
                    print(result.extracted_content)
                    print(f"\nError parsing JSON: {e}")
            else:
                print("Error:", result.error_message)
            
    except Exception as e:
        print(f"Error occurred: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_crawler())
