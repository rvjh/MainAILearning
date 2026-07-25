from typing import Annotated, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import AIMessage


checkpointer = MemorySaver()

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

graph = builder.compile(checkpointer=checkpointer)

thread_1 = {"configurable": {"thread_id": "123"}}
thread_2 = {"configurable": {"thread_id": "456"}}
# run the graph
result = graph.invoke({"messages": [{"role": "user", "content": "Hi I am Rohan"}], "counter": 10}, thread_1)
print(result)

result = graph.invoke({"messages": [{"role": "user", "content": "who am I?"}], "counter": 10}, thread_1)
print(result)

# run the graph
result = graph.invoke({"messages": [{"role": "user", "content": "Hi I am Sam"}], "counter": 10}, thread_2)
print(result)

result = graph.invoke({"messages": [{"role": "user", "content": "who am I?"}], "counter": 10}, thread_2)
print(result)


result = graph.invoke({"messages": [{"role": "user", "content": "who am I?"}], "counter": 10}, thread_1)
print(result)

print("Getting state for thread 1")
print("--------------------------------")
get_state = graph.get_state(thread_1)
print(get_state)