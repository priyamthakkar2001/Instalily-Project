from .base_agent import BaseAgent
from typing import Dict, Any, Optional

class ConversationState:
    def __init__(self):
        self.appliance_type: Optional[str] = None
        self.model_number: Optional[str] = None
        self.last_valid_menu: Optional[str] = None
        self.conversation_history: list = []

class FallbackAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.conversation_states: Dict[str, ConversationState] = {}
        self.services_menu = """Thank you. Here are the services I can provide for your {appliance}:
1. Want the product manual or care guide
2. Help searching a part for their product model
3. Looking for help with a problem/symptoms in the product
4. Looking for installation information
What kind of help do you need?"""

    def _get_or_create_state(self, session_id: str) -> ConversationState:
        if session_id not in self.conversation_states:
            self.conversation_states[session_id] = ConversationState()
        return self.conversation_states[session_id]

    def update_state(self, session_id: str, **kwargs):
        state = self._get_or_create_state(session_id)
        for key, value in kwargs.items():
            setattr(state, key, value)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        query = input_data.get("query", "")
        session_id = input_data.get("session_id", "default")
        state = self._get_or_create_state(session_id)
        
        # Update state from input data
        if "appliance_type" in input_data:
            state.appliance_type = input_data["appliance_type"]
        if "model_number" in input_data:
            state.model_number = input_data["model_number"]
            
        # Add query to conversation history
        state.conversation_history.append({"role": "user", "content": query})
        
        # If we have both appliance type and model number, show services menu
        if state.appliance_type and state.model_number:
            response = self.services_menu.format(appliance=state.appliance_type)
            return {
                "response": response,
                "state": {
                    "appliance_type": state.appliance_type,
                    "model_number": state.model_number,
                    "last_valid_menu": response
                }
            }
            
        # If we have appliance type but no model number
        if state.appliance_type and not state.model_number:
            return {
                "response": "Could you please provide your appliance's model number? It's usually found on a label inside the appliance.",
                "state": {"appliance_type": state.appliance_type}
            }
            
        # Default fallback - ask for appliance type
        return {
            "response": "I specialize in helping with refrigerators and dishwashers. Which appliance do you need help with?",
            "state": {}
        }
