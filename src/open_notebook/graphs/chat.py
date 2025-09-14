from typing import Annotated, Optional

from ai_prompter import Prompter
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import TypedDict

from ..domain.notebook import Notebook
from .utils import provision_langchain_model


class ThreadState(TypedDict):
    messages: Annotated[list, add_messages]
    notebook: Optional[Notebook]
    context: Optional[str]
    context_config: Optional[dict]


def call_model_with_messages(state: ThreadState, config: RunnableConfig) -> dict:
    try:
        # Log the incoming state for debugging
        print(f"[DEBUG] call_model_with_messages state: {state}")
        
        # Generate system prompt
        import os
        prompt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "prompts")
        system_prompt = Prompter(prompt_template="chat", prompt_dir=prompt_dir).render(data=state)
        
        # Prepare messages for the model
        messages = state.get("messages", [])
        payload = [SystemMessage(content=system_prompt)] + messages
        
        # Log the payload being sent to the model
        print(f"[DEBUG] Sending to model: {payload}")
        
        # Get the model
        model = provision_langchain_model(
            str(payload),
            config.get("configurable", {}).get("model_id"),
            "chat",
            max_tokens=2000,
        )
        
        # Get the AI response
        ai_message = model.invoke(payload)
        
        # Log the raw response
        print(f"[DEBUG] Raw AI response: {ai_message}")
        
        # Ensure we return the message in the correct format
        if hasattr(ai_message, 'content'):
            return {"messages": [ai_message]}
        elif isinstance(ai_message, dict) and 'messages' in ai_message:
            return ai_message
        else:
            # Fallback to ensure we always return the expected format
            return {"messages": [{"content": str(ai_message), "role": "assistant"}]}
            
    except Exception as e:
        print(f"[ERROR] in call_model_with_messages: {str(e)}")
        # Return an error message in the expected format
        return {"messages": [{"content": f"Error generating response: {str(e)}", "role": "assistant"}]}


# Create a simple in-memory saver for now
memory = MemorySaver()

# Create the graph
agent_state = StateGraph(ThreadState)
agent_state.add_node("agent", call_model_with_messages)
agent_state.add_edge(START, "agent")
agent_state.add_edge("agent", END)

# Compile the graph
graph = agent_state.compile(
    checkpointer=memory,
    interrupt_after=["agent"]  # Allow for streaming
)
