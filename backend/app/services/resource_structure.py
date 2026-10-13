from __future__ import annotations

import json
import re
from typing import Any


_CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_-]*\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_QUESTIONS_MARKER_RE = re.compile(
    r"<!--\s*QUESTIONS_JSON\s*-->\s*(.*?)\s*<!--\s*QUESTIONS_JSON_END\s*-->",
    re.IGNORECASE | re.DOTALL,
)


def extract_resource_structures(resource_type: str, content: str) -> dict[str, Any]:
    """Return structured views that the frontend can render without changing file formats."""
    data: dict[str, Any] = {}

    if resource_type == "mindmap":
        mermaid = extract_mermaid_mindmap(content)
        if mermaid:
            data["mermaid_source"] = mermaid
            tree = parse_mermaid_mindmap_to_tree(mermaid)
            if tree:
                data["mindmap_tree"] = tree

    if resource_type == "question_bank":
        questions = extract_questions_json(content)
        if questions is not None:
            data["questions_json"] = questions

    return data


def extract_mermaid_mindmap(content: str) -> str | None:
    for block in _CODE_BLOCK_RE.findall(content or ""):
        if "mindmap" in block.lower():
            return block.strip()

    lines = (content or "").splitlines()
    for idx, line in enumerate(lines):
        if line.strip().lower() == "mindmap":
            collected: list[str] = []
            for follow in lines[idx:]:
                if not follow.strip() and collected:
                    break
                collected.append(follow.rstrip())
            return "\n".join(collected).strip()
    return None


def parse_mermaid_mindmap_to_tree(mermaid_text: str) -> dict[str, Any] | None:
    lines = [
        line.rstrip("\n").replace("\t", "  ")
        for line in (mermaid_text or "").splitlines()
        if line.strip()
    ]
    if not lines:
        return None

    if lines[0].strip().lower() == "mindmap":
        lines = lines[1:]
    if not lines:
        return None

    root: dict[str, Any] | None = None
    stack: list[tuple[int, dict[str, Any]]] = []

    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        label = _clean_mermaid_label(stripped)
        if not label:
            continue

        node = {"label": label, "children": []}
        if root is None:
            root = node
            stack = [(indent, node)]
            continue

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else root
        parent.setdefault("children", []).append(node)
        stack.append((indent, node))

    return root


def extract_questions_json(content: str) -> Any | None:
    text = (content or "").strip()
    if not text:
        return None

    marked = _QUESTIONS_MARKER_RE.search(text)
    if marked:
        parsed = _json_loads_maybe(marked.group(1))
        if parsed is not None:
            return parsed

    parsed = _json_loads_maybe(text)
    if parsed is not None:
        return parsed

    for block in _CODE_BLOCK_RE.findall(text):
        parsed = _json_loads_maybe(block.strip())
        if parsed is not None:
            return parsed

    return None


def _json_loads_maybe(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _clean_mermaid_label(text: str) -> str:
    label = re.sub(r"^[\-*+]\s*", "", text).strip()
    wrapper_patterns = [
        r"^[\w-]*\(\((.*?)\)\)$",
        r"^[\w-]*\(\[(.*?)\]\)$",
        r"^[\w-]*\[(.*?)\]$",
        r"^[\w-]*\((.*?)\)$",
    ]
    for pattern in wrapper_patterns:
        match = re.match(pattern, label)
        if match:
            label = match.group(1).strip()
            break
    return label.strip("\"' ")
