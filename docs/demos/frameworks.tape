# Jev decisions as tools inside host-owned LangGraph and Pydantic AI loops, offline.
# Render from the repository root after `uv sync --frozen --all-extras`: vhs docs/demos/frameworks.tape
Output docs/demos/frameworks.gif

Source docs/demos/_settings.tape
Require python
Source docs/demos/_setup.tape

Type "# LangGraph ToolNode dispatches a Jev decision tool (serialized result):"
Enter
Type "python examples/langchain_decision.py | head -n 1 | python -m json.tool"
Enter
Wait+Screen@30s /"schema_version"/
Sleep 3s
Type "clear"
Enter
Type "# Pydantic AI agent calls the same decision as a function tool:"
Enter
Type "python examples/pydantic_ai_decision.py | head -n 2"
Enter
Wait+Screen@30s /advisory decision is recorded/
Sleep 3s
