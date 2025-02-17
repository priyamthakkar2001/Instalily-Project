from typing import Dict, Any, List
from .base_agent import BaseAgent
import logging
import json
import re
import os
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

class BaseHelpAgent(BaseAgent):
    """Base class for all help agents with common functionality"""
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"BaseHelpAgent processing input: {input_data}")
        return await self.process_content(input_data)

    async def process_content(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the content. Must be implemented by subclasses."""
        raise NotImplementedError

def find_most_relevant_product(products, target_type: str):
    """Find the most relevant product from the list of products based on target_type."""
    max_score = 0
    best_product = None
    
    for product in products:
        score = 0
        content = product.get('content', [])
        name = content[0].lower() if content else ''
        
        # Check if it matches the target type
        if target_type.lower() in name:
            score += 5
        
        # Check if it's an actual part vs accessories
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
    name = re.sub(r'[^\w\s-]', '', name)  # Remove special characters
    name = name.replace(' ', '-')  # Replace spaces with hyphens
    
    # Construct URL in the format: PS<number>-Brand-MfrNumber-Product-Name.htm
    url = f"https://www.partselect.com/{part_number}-Frigidaire-{manufacturer_number}-{name}.htm"
    url += f"?SourceCode=21&SearchTerm={model}&ModelNum={model}"
    
    return url

class PartsAgent(BaseHelpAgent):
    def __init__(self):
        super().__init__()
        # Initialize crawler configuration
        self.browser_cfg = BrowserConfig(
            headless=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        )
        
        # Initialize crawler run configuration
        self.crawl_config = None  # Will be set per request since it needs the part type

    def format_part_info(self, part_info):
        """Format part information in a structured way"""
        return f"""
<div class="part-info">
    <div class="info-line">
        <span class="info-label">Name:</span>
        <span class="info-value">{part_info['name']}</span>
    </div>
    <div class="info-line">
        <span class="info-label">Part Number:</span>
        <span class="info-value">PartSelect #: {part_info['part_number']}</span>
    </div>
    <div class="info-line">
        <span class="info-label">Manufacturer:</span>
        <span class="info-value">Manufacturer #: {part_info['manufacturer']}</span>
    </div>
    <div class="info-line">
        <span class="info-label">Description:</span>
        <span class="info-value">{part_info['description']}</span>
    </div>
    <div class="info-line price-line">
        <span class="info-label">Price:</span>
        <span class="info-value price-value">${part_info['price']}</span>
    </div>
    <a href="{part_info['url']}" class="part-link" target="_blank">View and purchase this part here →</a>
</div>

Would you like help finding any other parts? Is there anything else I can help you with?"""

    def format_services_list(self):
        """Format services list in a structured way"""
        return """
Thank you. Here are the services I can provide for your refrigerator:

<div class="services-list">
1. Want a specific diagram
2. Want the product manual or care guide
3. Help searching a part for their product model
4. Looking for help with a problem/symptoms in the product
5. Looking for installation information
</div>

<p class="question">What kind of help do you need?</p>
"""

    async def process_content(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            base_url = input_data.get("base_url", "")
            help_needed = input_data.get("details", "")
            model_number = input_data.get("model_number", "")
            
            if not all([base_url, help_needed, model_number]):
                return {
                    "response": "I need more information about what part you're looking for and your model number.",
                    "success": False
                }

            # Extract part name from help details using GPT
            messages = self.create_chat_messages(
                """Extract the specific part type from this request. Example: 'water filter', 'shelf', 'drawer'.
                Request: {help_needed}
                Return ONLY the part type, nothing else.""".format(help_needed=help_needed)
            )
            response = await self.llm.agenerate([messages])
            part_type = response.generations[0][0].text.strip().lower()
            
            # Create LLM extraction strategy for the specific part type
            llm_strategy = LLMExtractionStrategy(
                api_token=os.getenv("OPENAI_API_KEY"),
                provider="openai/gpt-4",
                extraction_type="block",
                instruction=f"""Find {part_type} products and related items for this refrigerator model. For each product found, extract in order:
                1. Product name
                2. PartSelect number
                3. Manufacturer number
                4. Description
                5. Location information
                6. Any discount information
                7. Current price
                8. Original price (if discounted)
                
                Format the response as a JSON array of objects with 'index', 'tag', and 'content' fields, where content is an array of the above information in order.""",
                chunk_token_threshold=800,
                overlap_rate=0.1,
                apply_chunking=True,
                input_format="markdown",
                extra_args={"temperature": 0.0, "max_tokens": 1000},
                verbose=True,
            )
            
            # Update crawler config with the extraction strategy
            self.crawl_config = CrawlerRunConfig(
                extraction_strategy=llm_strategy,
                cache_mode=CacheMode.BYPASS,
                process_iframes=False,
                remove_overlay_elements=True,
                excluded_tags=["form", "header", "footer"],
            )
            
            # Construct search URL
            search_url = f"{base_url}/Parts/?SearchTerm={part_type}"
            logger.info(f"Searching for parts at URL: {search_url}")

            try:
                async with AsyncWebCrawler(config=self.browser_cfg) as crawler:
                    # Crawl the URL
                    result = await crawler.arun(url=search_url, config=self.crawl_config)
                    
                    if result.success:
                        # Parse the JSON response
                        products = json.loads(result.extracted_content)
                        
                        # Find the most relevant product
                        best_product = find_most_relevant_product(products, part_type)
                        
                        if best_product:
                            content = best_product['content']
                            
                            # Construct response
                            part_info = {
                                'name': content[0],
                                'part_number': content[1],
                                'manufacturer': content[2],
                                'description': content[3] if len(content) > 3 else '',
                                'price': content[6] if len(content) > 6 else '',
                                'url': construct_product_url(content[1], content[2], content[0], model_number)
                            }
                            response_text = self.format_part_info(part_info)
                            return {"response": response_text, "success": True}
                        
                        return {
                            "response": f"I searched for {part_type} parts for your {model_number}, but couldn't find exact matches. You can view all available parts at: {base_url}\n\nWould you like help finding other parts?",
                            "success": True
                        }
                    else:
                        logger.error(f"Error in crawler: {result.error_message}")
                        return {
                            "response": f"I encountered an error while searching for {part_type} parts. Please try again or visit {base_url} directly.",
                            "success": False
                        }

            except Exception as e:
                logger.error(f"Error scraping parts: {str(e)}")
                return {
                    "response": f"I can help you find {part_type} parts for your {model_number}. Please visit: {search_url}\n\nWould you like help finding other parts?",
                    "success": True
                }

        except Exception as e:
            logger.error(f"Error in PartsAgent: {str(e)}", exc_info=True)
            return {
                "response": "I encountered an error while searching for parts. Please try again or visit the website directly.",
                "success": False
            }

@dataclass
class ManualContext:
    model_number: Optional[str] = None
    last_manual_url: Optional[str] = None
    last_manual_info: Optional[Dict] = None
    conversation_history: List[Dict] = field(default_factory=list)

class ManualAgent(BaseHelpAgent):
    """Agent for handling manual and documentation requests."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize contexts dictionary
        self.contexts = {}
        
        # Initialize crawler configuration
        self.browser_cfg = BrowserConfig(
            headless=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        )
        
        # LLM extraction configuration for manuals
        self.manual_extraction_config = LLMExtractionStrategy(
            api_token=os.getenv("OPENAI_API_KEY"),
            provider="openai/gpt-4",
            extraction_type="block",
            instruction="""Find manual download links. For each manual link, extract:
            1. Title (e.g. "INSTALLATION INSTRUCTIONS")
            2. Type (e.g. "Installation Manual")
            3. URL
            4. File size
            
            Look for text containing: manual, instructions, specifications, diagram, guide, specs
            Format: JSON array with index, tag="manual", content=[title, type, url, size]""",
            chunk_token_threshold=1000,
            overlap_rate=0.1,
            apply_chunking=True,
            input_format="markdown",
            extra_args={"temperature": 0.0, "max_tokens": 500},
            verbose=True,
        )

    def _get_or_create_context(self, session_id: str) -> ManualContext:
        if session_id not in self.contexts:
            self.contexts[session_id] = ManualContext()
        return self.contexts[session_id]

    def reset_context(self, session_id: str):
        self.contexts[session_id] = ManualContext()

    async def process_content(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the content and retrieve manuals."""
        try:
            model_number = input_data.get("model_number")
            base_url = input_data.get("base_url", "")
            session_id = input_data.get("session_id", "default")
            query = input_data.get("query", "")
            
            if not model_number:
                return {
                    "response": "I need your appliance's model number to find the right manuals. It's usually found on a label inside the appliance.",
                    "success": False
                }

            context = self._get_or_create_context(session_id)
            context.model_number = model_number
            context.conversation_history.append({"role": "user", "content": query})

            # If we have a last manual URL and user is asking for more details
            if context.last_manual_url and any(x in query.lower() for x in ["more", "details", "tell me more", "what's in it", "what is in it"]):
                try:
                    # Get additional details about the manual
                    crawler_config = CrawlerRunConfig(
                        extraction_strategy=self.manual_extraction_config,
                        cache_mode=CacheMode.BYPASS,
                        process_iframes=False,
                        remove_overlay_elements=True,
                        excluded_tags=["form", "header", "footer"],
                    )
                    
                    results = await self.crawler.run(context.last_manual_url, crawler_config)
                    if results and results.extractions:
                        manual_details = results.extractions[0]
                        response = self.format_manual_details(manual_details, context.last_manual_info)
                        context.conversation_history.append({"role": "assistant", "content": response})
                        return {"response": response, "success": True}
                except Exception as e:
                    logger.error(f"Error getting manual details: {str(e)}")
                    return {
                        "response": "I apologize, but I had trouble getting more details about that manual. Would you like to see other available manuals?",
                        "success": False
                    }

            # Construct the correct URL format for manuals
            # Use the base_url directly since it already contains the model number
            manual_url = base_url
            logger.info(f"Searching for manuals at: {manual_url}")
            
            # Configure crawler for manual extraction
            crawler_config = CrawlerRunConfig(
                extraction_strategy=self.manual_extraction_config,
                cache_mode=CacheMode.BYPASS,
                process_iframes=False,
                remove_overlay_elements=True,
                excluded_tags=["form", "header", "footer"],
            )

            # Crawl for manuals
            async with AsyncWebCrawler(config=self.browser_cfg) as crawler:
                # Crawl the URL
                result = await crawler.arun(url=manual_url, config=crawler_config)
                
                if not result or not result.success:
                    return {
                        "response": f"I apologize, but I couldn't find any manuals for model {model_number}. Please verify the model number and try again.",
                        "success": False
                    }

                # Process the results
                try:
                    manuals_data = json.loads(result.extracted_content)
                    if not isinstance(manuals_data, list):
                        manuals_data = [manuals_data]
                    
                    # Ensure all manual URLs are absolute
                    for manual in manuals_data:
                        if manual.get('content') and len(manual['content']) > 2:
                            url = manual['content'][2]
                            if isinstance(url, str):  # Make sure URL is a string
                                if not url.startswith('http'):
                                    manual['content'][2] = f"{base_url.rstrip('/')}/{url.lstrip('/')}"
                            elif isinstance(url, dict) and url.get('href'):  # Handle URL in dict format
                                href = url['href']
                                if not href.startswith('http'):
                                    manual['content'][2] = f"{base_url.rstrip('/')}/{href.lstrip('/')}"
                                else:
                                    manual['content'][2] = href

                    if not manuals_data:
                        return {
                            "response": "No manuals found for this model. Is there anything else I can help you with?",
                            "success": False
                        }

                    # Format response
                    response = "Here are the available manuals:\n\n"
                    for manual in manuals_data:
                        if manual.get('content'):
                            title = manual['content'][0]
                            type_ = manual['content'][1]
                            url = manual['content'][2]
                            # Handle URL being either string or dict
                            if isinstance(url, dict):
                                url = url.get('href', '')
                            size = manual['content'][3] if len(manual['content']) > 3 else ""
                            response += f"- {title} ({type_})\n"
                            response += f"  Size: {size}\n"
                            response += f"  Download: {url}\n\n"

                    return {
                        "response": response,
                        "success": True,
                        "manuals": manuals_data
                    }
                except json.JSONDecodeError:
                    logger.error("Failed to parse manual data JSON")
                    return {
                        "response": "I encountered an error while processing the manual information. Please try again.",
                        "success": False
                    }

        except Exception as e:
            logger.error(f"Error in ManualAgent process_content: {str(e)}")
            return {
                "response": "I encountered an error while searching for manuals. Please try again.",
                "success": False
            }

    def format_manuals_list(self, manuals: List[Dict[str, str]]) -> str:
        """Format the list of manuals in a structured way for display."""
        if not manuals:
            return "No manuals found for this model."

        formatted_output = """
<div class="manuals-section">
    <h3>Available Manuals and Guides</h3>
    <div class="manuals-list">
"""
        for i, manual in enumerate(manuals, 1):
            formatted_output += f"""
        <div class="manual-item">
            <div class="manual-title">
                <span class="manual-number">{i}.</span>
                <span class="manual-name">{manual['title']}</span>
            </div>
            <div class="manual-type">{manual['type']}</div>
            <div class="manual-description">{manual.get('description', '')}</div>
            <a href="{manual['url']}" class="manual-link" target="_blank">
                Download Manual →
            </a>
        </div>
"""
        
        formatted_output += """
    </div>
</div>

Is there anything specific you'd like to know about these manuals? Or would you like help with something else?
"""
        return formatted_output

    def format_manual_details(self, details: Dict[str, Any], manual_info: Dict[str, Any]) -> str:
        """Format detailed manual information."""
        return f"""
<div class="manual-details">
    <h3>{manual_info['title']}</h3>
    <div class="manual-content">
        <div class="manual-type">{manual_info['type']}</div>
        <div class="manual-description">{details.get('description', 'No detailed description available.')}</div>
        <div class="manual-sections">
            {details.get('sections', 'This manual covers basic operation and maintenance of your appliance.')}
        </div>
        <a href="{manual_info['url']}" class="manual-link" target="_blank">
            Download Full Manual →
        </a>
    </div>
</div>
"""

class SymptomsAgent(BaseHelpAgent):
    """Agent for handling symptom and troubleshooting requests."""
    def __init__(self):
        super().__init__()
        # Initialize crawler configuration
        self.browser_cfg = BrowserConfig(
            headless=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        )
        
        # LLM extraction configuration for symptoms
        self.symptoms_extraction_config = LLMExtractionStrategy(
            api_token=os.getenv("OPENAI_API_KEY"),
            provider="openai/gpt-4",
            extraction_type="block",
            instruction="""Extract symptom sections and their associated URLs from the page.
            Look for sections with symptom headings like:
            - "Common Symptoms"
            - "Troubleshooting"
            - "Problems"
            
            For each symptom section found, extract:
            1. The symptom title/heading
            2. The URL or anchor link for that section
            
            Format as JSON array:
            {
                "index": number,
                "tag": "symptom_link",
                "content": {
                    "symptom": "symptom description",
                    "url": "URL or anchor link to section"
                }
            }""",
            chunk_token_threshold=500,  # Reduced to handle less content
            overlap_rate=0.1,
            apply_chunking=True,
            input_format="markdown",
            extra_args={"temperature": 0.0, "max_tokens": 300},
            verbose=True
        )

    async def process_content(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the content and match symptoms to relevant sections."""
        try:
            help_needed = input_data.get("help_needed", "")
            details = input_data.get("details", "")
            base_url = input_data.get("base_url", "")
            
            if not help_needed:
                return {
                    "response": "Please describe the problem you're experiencing.",
                    "success": False
                }

            # Extract main symptom from help needed
            messages = self.create_chat_messages(
                f"""Extract the main symptom or problem from this text. Be concise and specific.
                Text: {details if details else help_needed}
                Response:"""
            )
            response = await self.llm.agenerate([messages])
            target_symptom = response.generations[0][0].text.strip().lower()

            # Create crawler run configuration
            crawl_config = CrawlerRunConfig(
                extraction_strategy=self.symptoms_extraction_config,
                cache_mode=CacheMode.BYPASS,
                process_iframes=False,
                remove_overlay_elements=True,
                excluded_tags=["form", "header", "footer"],
            )
            
            try:
                async with AsyncWebCrawler(config=self.browser_cfg) as crawler:
                    result = await crawler.arun(url=base_url, config=crawl_config)
                    
                    if not result.success or not result.extracted_content:
                        return {
                            "response": "I apologize, but I couldn't find any symptom information on this page.",
                            "success": False
                        }

                    # Process extracted content
                    symptoms_data = json.loads(result.extracted_content)
                    matching_links = []
                    
                    for item in symptoms_data:
                        content = item.get("content", {})
                        symptom = content.get("symptom", "").lower()
                        url = content.get("url", "")
                        
                        if target_symptom in symptom and url:
                            matching_links.append({
                                "symptom": content["symptom"],
                                "url": url if url.startswith("http") else f"{base_url}{url}"
                            })

                    if not matching_links:
                        return {
                            "response": f"I couldn't find specific sections about '{target_symptom}' on the page.",
                            "success": False
                        }

                    # Format response with matching links
                    response = self._format_symptom_links(matching_links)
                    return {
                        "response": response,
                        "success": True
                    }

            except Exception as e:
                logger.error(f"Error in crawler: {str(e)}")
                return {
                    "response": f"I encountered an error while searching. You can check the page directly at: {base_url}",
                    "success": False
                }

        except Exception as e:
            logger.error(f"Error in SymptomsAgent: {str(e)}")
            return {
                "response": "I encountered an error while processing your request. Please try again.",
                "success": False
            }

    def _format_symptom_links(self, matching_links: List[Dict[str, str]]) -> str:
        """Format the symptom links in a structured way"""
        response = """<div class="symptom-links">
    <h3>Relevant Troubleshooting Sections:</h3>
    <ul>"""
        
        for link in matching_links:
            response += f"""
        <li>
            <a href="{link['url']}" target="_blank">{link['symptom']}</a>
        </li>"""
            
        response += """
    </ul>
</div>
<p>Click on any link above to view detailed troubleshooting information for your problem. Need help with anything else?</p>"""
        
        return response

class InstallationAgent(BaseHelpAgent):
    """Agent for handling installation-related requests."""
    async def process_content(self, content, help_needed: str) -> Dict[str, Any]:
        installation_div = content.find(id="installation")
        if not installation_div:
            return {
                "response": "I apologize, but I couldn't find installation instructions for this model.",
                "success": False
            }
        
        instructions = installation_div.find_all('p')
        if instructions:
            response = "Here are the installation instructions:\n\n"
            for i, instruction in enumerate(instructions, 1):
                response += f"{i}. {instruction.text}\n"
            return {"response": response, "success": True}
        
        return {
            "response": "I apologize, but I couldn't find installation instructions for this model.",
            "success": False
        }
