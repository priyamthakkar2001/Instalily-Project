from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
import logging

logger = logging.getLogger(__name__)

class BaseAgent:
    def __init__(self, model_name: str = "gpt-3.5-turbo"):
        try:
            self.llm = ChatOpenAI(
                model_name=model_name,
                temperature=0.7
            )
            self.conversation_history: List[Dict[str, str]] = []
            logger.info(f"Initialized {self.__class__.__name__} with model {model_name}")
        except Exception as e:
            logger.error(f"Error initializing {self.__class__.__name__}: {str(e)}", exc_info=True)
            raise
    
    def add_to_history(self, role: str, content: str) -> None:
        """Add a message to the conversation history"""
        self.conversation_history.append({"role": role, "content": content})
    
    def set_conversation_history(self, history: List[Dict[str, Any]]) -> None:
        """Set the conversation history from another agent"""
        self.conversation_history = history

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the current conversation history"""
        return self.conversation_history

    def create_chat_messages(self, prompt: str) -> List[Any]:
        """Create a list of chat messages from the conversation history and current prompt"""
        messages = []
        
        # Add conversation history
        for msg in self.conversation_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        
        # Add the current prompt
        messages.append(HumanMessage(content=prompt))
        
        return messages
    
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the input. Must be implemented by subclasses."""
        raise NotImplementedError
