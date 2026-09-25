# Hero demo: the README quickstart, run offline with no API key.
# Render from the repository root after `uv sync --frozen --all-extras`: vhs docs/demos/quickstart.tape
Output docs/demos/quickstart.gif
Output docs/demos/quickstart.mp4

Source docs/demos/_settings.tape
Require python
Source docs/demos/_setup.tape

Type "# One typed yes/no judgment through the direct decision API, fully offline."
Enter
Sleep 500ms
Type "sed -n '/^async def main/,/print(result/p' examples/quickstart.py"
Enter
Sleep 4s
Type "python examples/quickstart.py"
Enter
Wait+Screen@20s /offline-model 1/
Sleep 3s
