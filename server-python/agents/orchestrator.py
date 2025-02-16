from typing import Dict, Any, List, Tuple
from .base_agent import BaseAgent
import logging

logger = logging.getLogger(__name__)

class Orchestrator1(BaseAgent):
    def __init__(self):
        super().__init__()
        self.category_prompt = """Determine if the user's query is related to refrigerators, dishwashers, or neither.
            Query: {query}
            Return ONLY ONE of these exact words: 'refrigerator', 'dishwasher', or 'other'.
            Response:"""

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        query = input_data.get("query", "")
        
        # Create messages for the LLM
        messages = self.create_chat_messages(self.category_prompt.format(query=query))
        
        # Get response from LLM
        response = await self.llm.agenerate([messages])
        category = response.generations[0][0].text.strip().lower()
        
        # Validate category
        if category not in ["refrigerator", "dishwasher", "other"]:
            category = "other"
        
        return {
            "category": category,
            "query": query
        }

class Orchestrator2(BaseAgent):
    def __init__(self):
        super().__init__()
        self.help_type_prompt = """Based on the help needed and context, determine which type of help agent should handle this request.
            Appliance type: {appliance_type}
            Model number: {model_number}
            Help needed: {help_needed}
            Additional details: {details}
            
            Choose ONLY ONE of these categories by matching the request to the most appropriate description:
            
            1. 'manual' - If user needs general product manual, user guide, or care instructions
            2. 'parts' - If user needs to:
               - Find specific replacement parts
               - Purchase parts (filters, shelves, etc.)
               - Get part numbers or prices
               - Find compatible parts
            3. 'symptoms' - If user has:
               - Problems or issues with the appliance
               - Error codes or warning lights
               - Performance issues
               - Troubleshooting needs
            4. 'installation' - If user needs:
               - Installation instructions
               - Setup guidance
               - Connection help
               - Placement instructions
            
            Return ONLY the category name in lowercase (diagram, manual, parts, symptoms, or installation).
            Response:"""

    def create_model_url(self, model_number: str) -> str:
        """Create the base URL for the model"""
        # Clean the model number
        model_number = model_number.strip().replace(" ", "")
        url = f"https://www.partselect.com/Models/{model_number}"
        logger.info(f"Created URL: {url} for model: {model_number}")
        return url

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Orchestrator2 received input: {input_data}")
        
        model_number = input_data.get("model_number", "")
        help_needed = input_data.get("help_needed", "")
        details = input_data.get("details", "")
        appliance_type = input_data.get("appliance_type", "appliance")
        session_id = input_data.get("session_id", "")
        
        # Store the services menu as the last valid menu
        last_valid_menu = """Thank you. Here are the services I can provide for your refrigerator:
1. Want the product manual or care guide
2. Help searching a part for their product model
3. Looking for help with a problem/symptoms in the product
4. Looking for installation information
What kind of help do you need?"""
        
        if not model_number or not help_needed:
            logger.error("Missing required fields: model_number or help_needed")
            # Pass context to fallback agent
            return {
                "category": "fallback",
                "appliance_type": appliance_type,
                "model_number": model_number,
                "last_valid_menu": last_valid_menu if model_number else None,
                "session_id": session_id
            }
        
        # Create base URL
        base_url = self.create_model_url(model_number)
        logger.info(f"Created base URL: {base_url}")
        
        # Create messages for the LLM
        prompt = self.help_type_prompt.format(
            appliance_type=appliance_type,
            model_number=model_number,
            help_needed=help_needed,
            details=details
        )
        logger.info(f"Generated prompt for LLM: {prompt}")
        
        messages = self.create_chat_messages(prompt)
        
        # Get response from LLM
        response = await self.llm.agenerate([messages])
        help_type = response.generations[0][0].text.strip().lower()
        logger.info(f"Raw LLM response for help type: {help_type}")
        
        # Clean up the help type - remove any "response:" prefix
        help_type = help_type.replace("response:", "").strip()
        logger.info(f"Cleaned help type: {help_type}")
        
        # Validate help type
        valid_help_types = ["manual", "parts", "symptoms", "installation"]
        if help_type not in valid_help_types:
            logger.warning(f"Invalid help type '{help_type}' for query: {help_needed}")
            # Default to parts if it's about finding/replacing parts
            if any(word in help_needed.lower() for word in ["part", "filter", "shelf", "drawer", "bin", "replacement"]):
                help_type = "parts"
                logger.info(f"Defaulted to 'parts' based on keywords in: {help_needed}")
            else:
                help_type = "manual"
                logger.info("Defaulted to 'manual' as fallback")
        
        result = {
            "help_type": help_type,
            "base_url": base_url,
            "help_needed": help_needed,
            "details": details,
            "model_number": model_number,
            "appliance_type": appliance_type
        }
        logger.info(f"Orchestrator2 returning: {result}")
        return result
