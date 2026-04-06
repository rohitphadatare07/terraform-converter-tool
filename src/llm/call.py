"""
Shared LLM invocation helper.

Different LLM backends return different types:
  - LangChain-wrapped models  → AIMessage  (has .content attribute)
  - Custom / raw API servers  → plain str
  - Some community adapters   → dict with a "content" key

This helper normalises all of them to a plain str so every agent
can do:   raw = llm_call(llm, messages)
"""
from __future__ import annotations

from typing import Any, List

from langchain_core.messages import BaseMessage


def llm_call(llm: Any, messages: List[BaseMessage]) -> str:
    """
    Invoke *llm* with *messages* and always return a plain string.

    Handles:
      - AIMessage / BaseChatModel response  → response.content
      - Plain str response                  → returned as-is
      - Dict response                       → response["content"] or str(response)
      - Anything else                       → str(response)
    """
    response = llm.invoke(messages)
    return _extract_text(response)


def _extract_text(response: Any) -> str:
    """Recursively unwrap a response into a plain string."""

    # LangChain AIMessage / any BaseMessage
    if hasattr(response, "content"):
        content = response.content
        # content itself might be a list of blocks (e.g. Anthropic tool-use)
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    parts.append(block.get("text", block.get("content", str(block))))
                else:
                    parts.append(str(block))
            return "".join(parts).strip()
        return str(content).strip()

    # Plain string (custom API servers often do this)
    if isinstance(response, str):
        return response.strip()

    # Dict with a content/text key
    if isinstance(response, dict):
        for key in ("content", "text", "message", "output", "result"):
            if key in response:
                return _extract_text(response[key])
        return str(response).strip()

    # List of responses — take the first one
    if isinstance(response, list) and response:
        return _extract_text(response[0])

    # Fallback: stringify whatever we got
    return str(response).strip()


def strip_markdown_fences(text: str) -> str:
    """Remove ```json / ``` fences that LLMs sometimes wrap their output in."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop the opening fence line (``` or ```json etc.)
        lines = lines[1:]
        # Drop the closing fence if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text