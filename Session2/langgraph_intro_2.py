from typing import Annotated, TypedDict, Optional
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import add_messages
# from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()


class StateNumber(TypedDict):
    x : int
    y : int
    node_1_res : Optional[float]
    node_2_res : Optional[float]
    node_3_res : Optional[float]
    node_4_res : Optional[float]


def node_1(state = StateNumber):
    add = state['x'] + state['y']
    return {"node_1_res": add}

def node_2(state = StateNumber):
    mul = state['x'] * state['y']
    return {"node_2_res": mul}

def node_3(state = StateNumber):
    div = state['x'] / state['y']
    return {"node_3_res": div}

def node_4(state = StateNumber):
    f = state['node_1_res'] + state['node_2_res'] + state['node_3_res']
    return {"node_4_res": f}


builder = StateGraph(StateNumber)

builder.add_node('node_1',node_1)
builder.add_node('node_2',node_2)
builder.add_node('node_3',node_3)
builder.add_node('node_4',node_4)

builder.add_edge(START, 'node_1')
builder.add_edge('node_1', 'node_2')
builder.add_edge('node_2', 'node_3')
builder.add_edge('node_3', 'node_4')
builder.add_edge('node_4', END)

graph = builder.compile()

# run the graph
result = graph.invoke({
    "x": 10,
    "y": 5
})
print(result)
## {'x': 10, 'y': 5, 'node_1_res': 15, 'node_2_res': 50, 'node_3_res': 2.0, 'node_4_res': 67.0}