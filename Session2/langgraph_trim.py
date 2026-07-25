from typing import Annotated, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, trim_messages


load_dotenv()

messages = [
    SystemMessage(content="you're a good assistant"),
    HumanMessage(content="hi! I'm bob"),
    AIMessage(content="hi!"),
    HumanMessage(content="I like vanilla ice cream"),
    AIMessage(content="nice"),
    HumanMessage(content="whats 2 + 2"),
    AIMessage(content="4"),
    HumanMessage(content="thanks"),
    AIMessage(content="no problem!"),
    HumanMessage(content="having fun?"),
    AIMessage(content="yes!"),
]

# Create trimmer
trimmer = trim_messages(
    max_tokens=65,
    strategy="last",
    token_counter=ChatGroq(model="llama-3.1-8b-instant"),
    include_system=True,
    allow_partial=False,
    start_on="human",
)

# Apply trimming
trimmed = trimmer.invoke(messages)
print(trimmed)


