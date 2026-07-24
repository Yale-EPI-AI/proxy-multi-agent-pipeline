#!/usr/bin/env python3
"""Render LLM interaction traces as a flowing conversation.

Reads a JSONL file of LLM call traces and renders them as a flowing
conversation: system prompt shown once, then each turn shows only the
new tool results and the assistant's next response — no repetition.

Usage:
    uv run python scripts/render_llm_traces.py outputs/WRR/llm_traces.jsonl
    uv run python scripts/render_llm_traces.py outputs/WRR/           # auto-finds
    uv run python scripts/render_llm_traces.py outputs/WRR/ --tail 5  # last 5 turns
"""

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.rule import Rule
from rich.syntax import Syntax

console = Console()

ROLE_STYLES = {
    "system": "bold blue",
    "user": "green",
    "assistant": "bold cyan",
    "tool": "yellow",
}

CALL_TYPE_LABELS = {
    "chat_completion": "Chat Completion",
    "chat_completion_sync": "Chat Completion (sync)",
    "chat_with_tools": "Chat with Tools",
    "deep_research": "Deep Research",
}


# ── Helpers ──────────────────────────────────────────────────────────────


def find_trace_file(path: Path) -> Path:
    if path.is_file():
        return path
    if path.is_dir():
        candidate = path / "llm_traces.jsonl"
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"No llm_traces.jsonl found in {path}")
    raise FileNotFoundError(f"Not found: {path}")


def load_entries(path: Path, call_type_filter: str | None, tail: int | None) -> list[dict]:
    raw = path.read_text(encoding="utf-8").strip().split("\n")
    if not raw or raw == [""]:
        return []
    entries = []
    for line in raw:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    entries.sort(key=lambda e: e.get("timestamp", ""))
    if call_type_filter:
        entries = [e for e in entries if e.get("call_type") == call_type_filter]
    if tail:
        entries = entries[-tail:]
    return entries


def msg_signature(msg: dict) -> tuple:
    """Return a stable identity for a message to detect duplicates."""
    role = msg.get("role", "")
    if role == "tool":
        cid = msg.get("tool_call_id", msg.get("name", ""))
        return ("tool", cid)
    return (role, str(msg.get("content", "")))


def print_message(msg: dict) -> None:
    """Print a conversation message as a rule + content (no box)."""
    role = msg.get("role", "?")
    style = ROLE_STYLES.get(role, "white")
    content = msg.get("content", "")

    if role == "tool":
        tid = msg.get("tool_call_id", "?")
        name = msg.get("name", "")
        title = f"Tool Result ({name})" if name else "Tool Result"
    else:
        title = role.capitalize()

    console.print(Rule(title=title, style=style))
    if content:
        console.print(content)
    else:
        console.print("[dim](empty)[/dim]")


def print_tool_definitions(tools: list) -> None:
    """Print tool definitions as a rule + indented list."""
    if not tools:
        return
    console.print(Rule(title=f"Tools ({len(tools)})", style="bright_cyan"))
    for t in tools:
        name = t.get("name") or (t.get("function") or {}).get("name", "?")
        desc = t.get("description") or (t.get("function") or {}).get("description", "")
        console.print(f"  [bold]{name}[/bold] — {desc}")


# ── Response rendering ───────────────────────────────────────────────────


def print_response(entry: dict) -> None:
    """Print the LLM response (text then any tool calls)."""
    resp = entry.get("response", {})
    error = entry.get("error")

    if error:
        console.print(Rule(title="Error", style="bold red"))
        console.print(f"[red]{error}[/red]")
        return

    text = resp.get("text") or ""
    if text:
        console.print(Rule(title="Assistant", style="bold cyan"))
        console.print(text)

    tool_uses = resp.get("tool_uses") or []
    for i, tu in enumerate(tool_uses, 1):
        name = tu.get("name", "?")
        inp = tu.get("input", {})
        console.print(Rule(title=f"Tool Call #{i}: {name}", style="bright_yellow"))
        console.print(Syntax(
            json.dumps(inp, indent=2, ensure_ascii=False),
            "json",
            theme="monokai",
            word_wrap=True,
        ))

    if entry.get("call_type") == "deep_research" and not error:
        iid = resp.get("interaction_id", "?")
        console.print(Rule(title="Deep Research Submitted", style="bold magenta"))
        console.print(f"Interaction ID: {iid}")

    if not text and not tool_uses:
        console.print("[dim](empty response)[/dim]")


# ── Session rendering ────────────────────────────────────────────────────


def is_new_session(entry: dict, seen_sigs: set) -> bool:
    """Heuristic: new session if the entry's first request message is unseen."""
    msgs = entry.get("request", {}).get("messages", [])
    if msgs:
        return msg_signature(msgs[0]) not in seen_sigs
    return True


def render_conversation(entries: list[dict]) -> None:
    if not entries:
        console.print("[yellow]No entries to render.[/yellow]")
        return

    seen_sigs: set = set()
    seen_systems: set = set()
    tools_shown = False
    previous_session_index = -1
    session_index = -1

    for entry in entries:
        req = entry.get("request", {})

        # Detect session boundaries
        if is_new_session(entry, seen_sigs):
            session_index += 1
            tools_shown = False
            if session_index > previous_session_index + 1:
                console.print()
            previous_session_index = session_index

            # Session header
            label = CALL_TYPE_LABELS.get(entry.get("call_type", ""), entry.get("call_type", ""))
            header_text = (
                f" Session {session_index + 1}: {label} "
                f"  {entry.get('model', '?')} ({entry.get('provider', '?')})"
                f"  [{entry.get('duration_ms', 0)} ms] "
            )
            console.print(Rule(header_text, style="bright_blue"))
            ts = entry.get("timestamp", "")
            if ts:
                console.print(f"  [dim]{ts}[/dim]")

            # System prompt (show once per session)
            system = req.get("system")
            if system and system not in seen_systems:
                seen_systems.add(system)
                console.print(Rule(title="System Prompt", style="bold blue"))
                console.print(system)

        # Process request messages — only those not yet seen
        new_in_request = False
        for msg in req.get("messages", []):
            sig = msg_signature(msg)
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                print_message(msg)
                new_in_request = True

        # Tool definitions (once per session)
        if not tools_shown:
            print_tool_definitions(req.get("tools") or [])
            if req.get("tools"):
                tools_shown = True

        # Response (always shown)
        print_response(entry)

        # Register response text so it won't re-render in next entry's request
        resp = entry.get("response", {})
        if resp.get("text"):
            seen_sigs.add(("assistant", resp["text"]))


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render LLM interaction traces as a flowing conversation."
    )
    parser.add_argument("path", type=str, help="Path to JSONL file or output directory")
    parser.add_argument("--tail", "-n", type=int, default=None, help="Show only last N entries")
    parser.add_argument("--call-type", "-t", type=str, default=None, help="Filter by call type")
    parser.add_argument("--no-color", action="store_true", help="Disable color")
    args = parser.parse_args()

    if args.no_color:
        console.no_color = True

    trace_path = find_trace_file(Path(args.path))
    entries = load_entries(trace_path, args.call_type, args.tail)

    if not entries:
        console.print("[yellow]No entries found.[/yellow]")
        return

    render_conversation(entries)

    console.print()
    console.print(f"[dim]{len(entries)} entries from {trace_path}[/dim]")


if __name__ == "__main__":
    main()
