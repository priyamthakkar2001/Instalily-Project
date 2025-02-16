from typing import Dict, Any, Optional
from .base_agent import BaseAgent

class ApplianceAgent(BaseAgent):
    def __init__(self, appliance_type: str):
        super().__init__()
        self.appliance_type = appliance_type
        self.model_number = None
        self.services = [
            "1. Want the product manual or care guide",
            "2. Help searching a part for their product model",
            "3. Looking for help with a problem/symptoms in the product",
            "4. Looking for installation information"
        ]
        
        self.info_extraction_prompt = """Based on the conversation history and current query, determine:
            1. If a model number is mentioned (format: alphanumeric string)
            2. What type of help is needed (must be one of: diagram, manual, parts, symptoms, installation)
            3. The specific request details
            
            Conversation history:
            {conversation_history}
            
            Current query: {current_query}
            
            Common help type keywords:
            - manual: manual, guide, documentation, product manual, care guide
            - parts: part, filter, shelf, drawer, replacement
            - symptoms: problem, issue, error, not working, broken
            - installation: install, setup, connect, placement
            
            If both model number and help type are provided, respond in this format:
            MODEL: <model_number>
            HELP: <help_type>
            DETAILS: <specific_details>
            
            If only model number is provided, respond with just:
            MODEL: <model_number>
            
            If the user is selecting from the services list, match their response to the appropriate help type.
            For example, if they say "want the product manual", respond with:
            MODEL: <stored_model_number>
            HELP: manual
            DETAILS: General product manual and care guide
            
            If information is missing, ask the user a specific question to get the missing information.
            If asking for model number, remind them it's usually found on a label inside the appliance.
            Response:"""

    def format_history(self) -> str:
        """Format conversation history for the prompt"""
        history = []
        for msg in self.conversation_history:
            role = "User" if msg["role"] == "user" else "Assistant"
            history.append(f"{role}: {msg['content']}")
        return "\n".join(history)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        query = input_data.get("query", "")
        self.add_to_history("user", query)
        
        # If this is the first message, ask for model number
        if len(self.conversation_history) == 1:
            intro_msg = (
                f"I can help you with your {self.appliance_type}. Could you please provide your appliance's model number? "
                f"It's usually found on a label inside the appliance."
            )
            self.add_to_history("assistant", intro_msg)
            return {"response": intro_msg, "complete": False}
        
        # Create messages for the LLM
        messages = self.create_chat_messages(
            self.info_extraction_prompt.format(
                conversation_history=self.format_history(),
                current_query=query
            )
        )
        
        # Get response from LLM
        response = await self.llm.agenerate([messages])
        result = response.generations[0][0].text.strip()
        
        # Extract and validate model number if present
        if "MODEL:" in result:
            model_line = [line for line in result.split("\n") if line.startswith("MODEL:")][0]
            model_number = model_line.replace("MODEL:", "").strip()
            
            # Validate model number
            if model_number.lower() in ['n/a', 'unknown', 'none', ''] or len(model_number) < 4 or not any(c.isalnum() for c in model_number):
                error_msg = f"That doesn't appear to be a valid model number. Could you please double-check the model number on your appliance? It's usually found on a label inside the {self.appliance_type}."
                self.add_to_history("assistant", error_msg)
                return {"response": error_msg, "complete": False}
            
            # Store valid model number
            self.model_number = model_number
            
            # If we only have model number and no help type, show services
            if "HELP:" not in result:
                services_msg = (
                    f"Thank you. Here are the services I can provide for your {self.appliance_type}:\n"
                    + "\n".join(self.services)
                    + "\n\nWhat kind of help do you need?"
                )
                self.add_to_history("assistant", services_msg)
                return {"response": services_msg, "complete": False}
        
        # If we have both model number and help type
        if "MODEL:" in result and "HELP:" in result and "DETAILS:" in result:
            help_line = [line for line in result.split("\n") if line.startswith("HELP:")][0]
            details_line = [line for line in result.split("\n") if line.startswith("DETAILS:")][0]
            
            help_needed = help_line.replace("HELP:", "").strip()
            details = details_line.replace("DETAILS:", "").strip()
            
            self.add_to_history("assistant", f"I'll help you find {help_needed} information for model {self.model_number}. Specifically about: {details}")
            
            return {
                "response": f"I'll help you find {help_needed} information for model {self.model_number}. Specifically about: {details}",
                "complete": True,
                "model_number": self.model_number,
                "help_needed": help_needed,
                "details": details,
                "appliance_type": self.appliance_type
            }
        
        # If no model number yet, ask for it
        if "MODEL:" not in result:
            model_msg = f"Could you please provide your {self.appliance_type}'s model number? It's usually found on a label inside the appliance."
            self.add_to_history("assistant", model_msg)
            return {"response": model_msg, "complete": False}
        
        # If we have model but no help type selected
        if self.model_number:
            # Check if the current query matches any of the service options
            query_lower = query.lower()
            help_type = None
            details = None
            
            if "manual" in query_lower or "guide" in query_lower:
                help_type = "manual"
                details = "General product manual and care guide"
            elif "part" in query_lower:
                help_type = "parts"
                details = "Part information and replacement"
            elif any(word in query_lower for word in ["problem", "symptom", "issue", "error"]):
                help_type = "symptoms"
                details = "Troubleshooting and problem resolution"
            elif "install" in query_lower or "setup" in query_lower:
                help_type = "installation"
                details = "Installation and setup instructions"
            
            if help_type:
                self.add_to_history("assistant", f"I'll help you find {help_type} information for model {self.model_number}. Specifically about: {details}")
                return {
                    "response": f"I'll help you find {help_type} information for model {self.model_number}. Specifically about: {details}",
                    "complete": True,
                    "model_number": self.model_number,
                    "help_needed": help_type,
                    "details": details,
                    "appliance_type": self.appliance_type
                }
            
        services_msg = (
            f"What kind of help do you need? Here are the services I can provide:\n"
            + "\n".join(self.services)
        )
        self.add_to_history("assistant", services_msg)
        return {"response": services_msg, "complete": False}

class FallbackAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.fallback_prompt = """The user's query is not related to refrigerators or dishwashers. 
            Provide a polite response explaining that we only handle refrigerator and dishwasher related queries.
            Suggest that they provide a query related to refrigerators or dishwashers.
            
            User query: {query}
            Response:"""

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        query = input_data.get("query", "")
        
        # Create messages for the LLM
        messages = self.create_chat_messages(self.fallback_prompt.format(query=query))
        
        # Get response from LLM
        response = await self.llm.agenerate([messages])
        result = response.generations[0][0].text.strip()
        
        self.add_to_history("assistant", result)
        return {
            "response": result,
            "complete": True
        }
