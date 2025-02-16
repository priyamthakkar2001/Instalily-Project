from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import uvicorn
import logging
from dotenv import load_dotenv
import os

# Configure logging first
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(verbose=True)

# Debug environment variables
api_key = os.getenv("OPENAI_API_KEY")
logger.debug(f"API Key loaded: {api_key[:8]}..." if api_key else "No API key found")

# Verify OpenAI API key is set
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

from agents.orchestrator import Orchestrator1, Orchestrator2
from agents.appliance_agent import ApplianceAgent, FallbackAgent
from agents.help_agents import (
    ManualAgent,
    PartsAgent,
    SymptomsAgent,
    InstallationAgent
)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agents
orchestrator1 = Orchestrator1()
orchestrator2 = Orchestrator2()
refrigerator_agent = ApplianceAgent("refrigerator")
dishwasher_agent = ApplianceAgent("dishwasher")
fallback_agent = FallbackAgent()

# Initialize help agents
help_agents = {
    "manual": ManualAgent(),
    "parts": PartsAgent(),
    "symptoms": SymptomsAgent(),
    "installation": InstallationAgent()
}

# Store conversation state
conversation_state = {}

class ChatRequest(BaseModel):
    userQuery: str
    sessionId: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    role: str = "assistant"
    content: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        session_id = request.sessionId or "default"
        logger.info(f"Received user query for session {session_id}: {request.userQuery}")
        
        # Initialize or get session state
        if session_id not in conversation_state:
            conversation_state[session_id] = {
                "current_agent": None,
                "category": None,
                "model_number": None,
                "help_type": None
            }
        
        state = conversation_state[session_id]
        
        # If we're in a conversation with an appliance agent, continue with it
        if state["current_agent"] and state["category"] in ["refrigerator", "dishwasher"]:
            logger.info(f"Continuing conversation with {state['category']} Agent...")
            appliance_agent = refrigerator_agent if state["category"] == "refrigerator" else dishwasher_agent
            appliance_result = await appliance_agent.process({"query": request.userQuery})
            
            # If the appliance agent is still gathering information, continue the conversation
            if not appliance_result.get("complete", False):
                return ChatResponse(
                    role="assistant",
                    content=appliance_result["response"]
                )
            
            # Only proceed to help agent if we have both model number and help type
            if "model_number" in appliance_result and "help_needed" in appliance_result:
                # Step 3: Use Orchestrator2 to determine help type and create URL
                logger.info("Processing with Orchestrator2...")
                orchestrator2_result = await orchestrator2.process({
                    "model_number": appliance_result["model_number"],
                    "help_needed": appliance_result["help_needed"],
                    "details": appliance_result.get("details", ""),
                    "appliance_type": state["category"]  # Pass appliance type (refrigerator/dishwasher)
                })
                
                help_type = orchestrator2_result["help_type"]
                logger.info(f"Using {help_type.capitalize()} Help Agent...")
                
                if help_type in help_agents:
                    help_agent = help_agents[help_type]
                    help_result = await help_agent.process({
                        "base_url": orchestrator2_result["base_url"],
                        "help_needed": orchestrator2_result["help_needed"],
                        "details": orchestrator2_result.get("details", ""),
                        "model_number": appliance_result["model_number"],
                        "appliance_type": state["category"]
                    })
                    
                    # Reset state after getting help
                    conversation_state[session_id] = {
                        "current_agent": None,
                        "category": None,
                        "model_number": None,
                        "help_type": None
                    }
                    
                    return ChatResponse(
                        role="assistant",
                        content=help_result["response"] + "\n\nIs there anything else I can help you with?"
                    )
            
            # If we don't have complete information, continue the conversation
            return ChatResponse(
                role="assistant",
                content=appliance_result["response"]
            )
        
        # If no ongoing conversation or previous conversation completed, start new
        logger.info("Processing with Orchestrator1...")
        category_result = await orchestrator1.process({"query": request.userQuery})
        state["category"] = category_result["category"]
        logger.info(f"Orchestrator1 determined category: {state['category']}")
        
        # Handle non-appliance queries with fallback agent
        if state["category"] == "other":
            logger.info("Using Fallback Agent...")
            fallback_result = await fallback_agent.process({
                "query": request.userQuery,
                "session_id": session_id,
                "appliance_type": state.get("category"),
                "model_number": state.get("model_number")
            })
            
            # Update state with fallback agent's state
            if "state" in fallback_result:
                state.update(fallback_result["state"])
            
            return ChatResponse(
                role="assistant",
                content=fallback_result["response"]
            )
        
        # Start conversation with appropriate appliance agent
        state["current_agent"] = state["category"]
        appliance_agent = refrigerator_agent if state["category"] == "refrigerator" else dishwasher_agent
        logger.info(f"Starting conversation with {state['category']} Agent...")
        appliance_result = await appliance_agent.process({"query": request.userQuery})
        
        return ChatResponse(
            role="assistant",
            content=appliance_result["response"]
        )
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return ChatResponse(
            role="assistant",
            content="Sorry, I encountered an error while processing your request. Please try again."
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
