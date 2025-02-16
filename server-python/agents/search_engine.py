from typing import Dict, Optional
import os
import logging
from urllib.parse import quote
from crawl4ai import (
    BrowserConfig,
    AsyncWebCrawler,
    CrawlerRunConfig,
    LLMExtractionStrategy
)
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import json

logger = logging.getLogger(__name__)

class PartInfo(BaseModel):
    name: Optional[str] = None
    part_number: Optional[str] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    description: Optional[str] = None
    availability: Optional[str] = None
    url: Optional[str] = None
    installation_steps: Optional[List[str]] = None
    installation_videos: Optional[List[str]] = None
    installation_tips: Optional[List[str]] = None
    safety_precautions: Optional[List[str]] = None

class SearchEngine:
    BASE_URL = "https://www.partselect.com"

    def __init__(self):
        self.browser_config = BrowserConfig(
            headless=True
        )

    @staticmethod
    def _create_extraction_prompt() -> str:
        """Create a focused extraction prompt"""
        return """Extract product information from the HTML content. Focus on:
        1. Product name and part number
        2. Current and original prices
        3. Product description
        4. Availability status
        5. Installation instructions and videos
        6. Product URL

        Format numbers without currency symbols. Extract only factual information, no marketing text.
        If information is not found, leave it empty."""

    async def _scrape_with_crawl4ai(self, url: str) -> Dict:
        """Optimized scraping with Crawl4AI"""
        try:
            logger.info(f"Starting optimized scraping for URL: {url}")
            
            # Configure extraction strategy
            extraction_strategy = LLMExtractionStrategy(
                provider="openai/gpt-3.5-turbo",
                api_token=os.getenv("OPENAI_API_KEY"),
                instruction=self._create_extraction_prompt(),
                schema=PartInfo.model_json_schema(),
                verbose=True,
                temperature=0.3
            )

            # Configure crawler run
            run_config = CrawlerRunConfig(
                extraction_strategy=extraction_strategy,
                max_retries=1
            )

            # Start scraping
            async with AsyncWebCrawler(config=self.browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)

                if not result or not result.extracted_content:
                    logger.warning(f"No content found for URL: {url}")
                    return {"error": "No content found"}

                # Parse the extracted content
                extracted_data = result.extracted_content
                if isinstance(extracted_data, str):
                    try:
                        extracted_data = json.loads(extracted_data)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse extracted content as JSON")
                        return {"error": "Failed to parse content"}

                # Ensure we have a list of parts
                if not isinstance(extracted_data, list):
                    extracted_data = [extracted_data]

                # Combine the data
                combined_data = self._combine_extracted_data(extracted_data)
                
                logger.info(f"Successfully extracted {len(extracted_data)} data blocks")
                return combined_data

        except Exception as e:
            logger.error(f"Error in _scrape_with_crawl4ai: {str(e)}")
            return {"error": f"Failed to scrape content: {str(e)}"}

    def _combine_extracted_data(self, extracted_data: List[Dict]) -> Dict:
        """Combine extracted data blocks intelligently"""
        combined = {
            "parts": [],
            "installation": {},
            "support": {}
        }

        for data in extracted_data:
            # Process part information
            if "name" in data and "part_number" in data:
                combined["parts"].append(data)
            
            # Process installation information
            if any(key in data for key in ["installation_steps", "installation_videos"]):
                combined["installation"].update({
                    k: v for k, v in data.items() 
                    if k.startswith("installation_") and v is not None
                })
            
            # Process support information
            if any(key in data for key in ["manuals", "guides", "troubleshooting"]):
                combined["support"].update({
                    k: v for k, v in data.items()
                    if k in ["manuals", "guides", "troubleshooting", "videos"] and v is not None
                })

        return combined

    async def scrape_partselect(self, model_number: str, part_type: Optional[str] = None) -> Dict:
        """Scrape PartSelect website for parts information"""
        try:
            # First get model information
            model_url = f"{self.BASE_URL}/Models/{model_number}"
            logger.info(f"Fetching model info from: {model_url}")
            
            model_data = await self._scrape_with_crawl4ai(model_url)
            if not model_data or "error" in model_data:
                return {"error": f"Could not find model {model_number}"}
            
            # Get specific part information
            search_url = f"{self.BASE_URL}/PS3412266-Frigidaire-WF3CB-Refrigerator-Water-Filter.htm?SourceCode=21&SearchTerm={model_number}&ModelNum={model_number}"
            if part_type == "water_filter":
                search_url = f"{self.BASE_URL}/PS3412266-Frigidaire-WF3CB-Refrigerator-Water-Filter.htm?SourceCode=21&SearchTerm={model_number}&ModelNum={model_number}"
            elif part_type == "ice_maker":
                search_url = f"{self.BASE_URL}/PS11722735-Frigidaire-Ice-Maker-Assembly.htm?SourceCode=21&SearchTerm={model_number}&ModelNum={model_number}"
            
            logger.info(f"Fetching parts from: {search_url}")
            parts_data = await self._scrape_with_crawl4ai(search_url)
            
            if not parts_data or "error" in parts_data:
                return {"error": "Could not find parts information"}
            
            return {
                "sections": {
                    "parts": parts_data.get("parts", [])
                }
            }

        except Exception as e:
            logger.error(f"Error in scrape_partselect: {str(e)}")
            return {"error": "An error occurred while fetching parts information"}

    async def scrape_support_page(self, support_url: str) -> Dict:
        """Scrape product support page"""
        try:
            logger.info(f"Fetching support materials from: {support_url}")
            
            support_data = await self._scrape_with_crawl4ai(support_url)
            if not support_data or "error" in support_data:
                return {"error": "Could not find support materials"}
            
            return support_data.get("support", {})

        except Exception as e:
            logger.error(f"Error in scrape_support_page: {str(e)}")
            return {"error": "An error occurred while fetching support materials"}
