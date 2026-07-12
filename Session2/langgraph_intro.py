from typing import Annotated, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
# from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    model="llama-3.1-8b-instant", 
    temperature=0)


class State(TypedDict):
    messages: Annotated[list[dict], add_messages]
    counter: int


def call_llm(state: State):
    output = llm.invoke(state["messages"])
    count = state.get("counter", 0) + 1
    return {"messages": [output], "counter": count}


builder = StateGraph(State)

# define a node
builder.add_node("llm", call_llm)

# define connections
builder.add_edge(START, "llm")
builder.add_edge("llm", END)

graph = builder.compile()

# run the graph
result = graph.invoke({"messages": [{"role": "user", "content": "Hello, how are you?"}], "counter": 10})
print(result)
