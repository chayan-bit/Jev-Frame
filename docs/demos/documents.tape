# One reusable document-evidence package bound to two host catalogs.
# Render from the repository root after `uv sync --frozen --all-extras`: vhs docs/demos/documents.tape
Output docs/demos/documents.gif

Source docs/demos/_settings.tape
Require python
Source docs/demos/_setup.tape

Type "# Bind the generic document-evidence package to two different catalogs:"
Enter
Type "sed -n '/^def build_examples/,/^$/p' examples/document_evidence.py"
Enter
Sleep 3s
Type "python examples/document_evidence.py"
Enter
Wait+Screen@20s /no core changes/
Sleep 3s
