"""
Demo: Tool Calling with Groq + LangChain

Tools:
- DuckDuckGo Search
- Wikipedia
- Calculator
"""

from dotenv import load_dotenv

load_dotenv()

from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper

from langchain_core.messages import (
    HumanMessage,
    ToolMessage,
)

from common import calculator, get_model, show

# ----------------------------------------------------
# Tools
# ----------------------------------------------------

search = DuckDuckGoSearchRun()

wikipedia = WikipediaQueryRun(
    api_wrapper=WikipediaAPIWrapper(
        top_k_results=1,
        doc_content_chars_max=500,
    )
)

TOOLS = [
    search,
    wikipedia,
    calculator,
]

BY_NAME = {tool.name: tool for tool in TOOLS}


# ----------------------------------------------------
# Agent
# ----------------------------------------------------

def run(question: str):

    llm = get_model()

    model = llm.bind_tools(TOOLS)

    messages = [
        HumanMessage(content=question)
    ]

    for _ in range(5):

        ai_msg = model.invoke(messages)

        messages.append(ai_msg)

        print("\nAssistant:")
        print(ai_msg.content)

        if not ai_msg.tool_calls:
            break

        for call in ai_msg.tool_calls:

            print(f"\nCalling tool: {call['name']}")
            print(call["args"])

            tool = BY_NAME[call["name"]]

            try:
                result = tool.invoke(call["args"])

                print("Tool Result:")
                print(result)

                messages.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=call["id"],
                    )
                )

            except Exception as e:

                print("Tool Error:", e)

                messages.append(
                    ToolMessage(
                        content=f"Tool Error: {e}",
                        tool_call_id=call["id"],
                    )
                )

    print("\nFinal Answer:\n")
    print(messages[-1].content)

    return messages


if __name__ == "__main__":

    print("=" * 80)
    print("Question 1")
    print("=" * 80)

    msgs = run(
        "What was Buzz Aldrin most famous for?"
    )

    show(msgs)

    print("\n" + "=" * 80)
    print("Question 2")
    print("=" * 80)

    msgs = run(
        "Search for the current population of Japan and divide it by 1000 using the calculator."
    )

    show(msgs)