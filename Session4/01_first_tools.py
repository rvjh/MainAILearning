from typing import Annotated, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
# from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    filter_messages, ToolMessage
)


load_dotenv()

llm = ChatGroq(
    model="llama-3.1-8b-instant", 
    temperature=0)


@tool
def multiply(x: float, y: float) -> float:
    """Multiply 'x' times 'y'."""
    return x*y

@tool
def add(x: float, y: float) -> float:
    """Add 'x' times 'y'."""
    return x+y

llm_with_tools = llm.bind_tools([multiply,add])

messages = [
    HumanMessage(content = "what is 11*12?")
]

ai_msg = llm_with_tools.invoke(messages)
messages.append(ai_msg)

print(f"Output for first message is {ai_msg}")

tool_names = {"multiply": multiply, "add": add}

for call in ai_msg.tool_calls:
    print(f"Tool call name: {call["name"]}")
    print(f"Tool call arguments: {call["args"]}")
    tool_result = tool_names[call["name"]].invoke(call["args"])
    messages.append(ToolMessage(content=tool_result, tool_call_id=call["id"]))
    print(f"Tool result: {tool_result}")

# Pass 3
final_result = llm_with_tools.invoke(messages)
print(f"Final result: {final_result}")


