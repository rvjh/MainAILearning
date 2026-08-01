## Run in the below manner 

First RUn the server : python fast_mcp.py 

then run others with python 

Note : for fast_mcp.py it may throw error. so use sys. or the path (D:\Mainfold_AI_Bootcamp\Orientation\MainAILearning\Session5\fast_mcp.py) - see code 

#### Output :

MCP Tools Loaded:
- add
- multiply
- search_docs_by_lang_chain
- query_docs_filesystem_docs_by_lang_chain
- submit_feedback

Type exit to quit

You: what is 100 * 3

DEBUG TOOL CALLS:
[{'name': 'multiply', 'args': {'a': 100, 'b': 3}, 'id': 'ensqgcwbx', 'type': 'tool_call'}]

DEBUG TOOL CALLS:
[]

Assistant: The result of 100 * 3 is 300.
You: add it with 100

DEBUG TOOL CALLS:
[{'name': 'add', 'args': {'a': 300, 'b': 100}, 'id': '3mfkxe450', 'type': 'tool_call'}]

DEBUG TOOL CALLS:
[]

Assistant: The result of 300 + 100 is 400.
You: exit