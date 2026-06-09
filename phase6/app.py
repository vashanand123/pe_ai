"""Phase 6 — Streamlit UI for pe-ai.

Chat-style interface over the Phase 5 agent. Shows the agent's tool calls
in real time so the user can see how Claude is constructing its answer.

Run from the pe_ai/ directory:
    uv run streamlit run phase6/app.py

Opens at http://localhost:8501
"""

import json
import os
import sys
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from phase5.agent import MODEL, SYSTEM_PROMPT, TOOL_FNS, TOOLS  # noqa: E402

load_dotenv()


st.set_page_config(page_title="pe-ai", page_icon="📊", layout="wide")
st.title("📊 pe-ai")
st.caption("Expert PE fund AI assistant — DuckDB + ChromaDB + Claude")


def init_state() -> None:
    if "history" not in st.session_state:
        st.session_state.history = []
    if "agent_messages" not in st.session_state:
        st.session_state.agent_messages = []
    if "client" not in st.session_state:
        st.session_state.client = anthropic.Anthropic()


def run_agent_streaming(question: str, max_iterations: int = 20):
    """Drive the agent loop, yielding events for the UI to render.

    Conversation history is kept in st.session_state.agent_messages so
    follow-up questions can reference prior turns (pronouns, "those funds",
    "what about Fund II", etc.).
    """
    st.session_state.agent_messages.append({"role": "user", "content": question})
    messages = st.session_state.agent_messages
    client = st.session_state.client

    for i in range(max_iterations):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        for block in response.content:
            if block.type == "text" and block.text.strip():
                yield {"kind": "text", "text": block.text}

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            yield {"kind": "done", "iterations": i + 1, "usage": response.usage}
            return

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                yield {"kind": "tool_call", "name": block.name, "input": block.input}
                try:
                    result = TOOL_FNS[block.name](block.input)
                    yield {"kind": "tool_result", "name": block.name, "result": result}
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )
                except Exception as e:
                    yield {"kind": "tool_error", "name": block.name, "error": str(e)}
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        }
                    )

        if tool_results:
            messages.append({"role": "user", "content": tool_results})


def render_event(event: dict) -> None:
    kind = event["kind"]
    if kind == "text":
        st.markdown(event["text"])
    elif kind == "tool_call":
        with st.expander(f"🔧 Tool call — `{event['name']}`", expanded=False):
            st.code(json.dumps(event["input"], indent=2), language="json")
    elif kind == "tool_result":
        result_str = json.dumps(event["result"], default=str, indent=2)
        with st.expander(
            f"📥 Tool result — `{event['name']}` ({len(result_str)} chars)",
            expanded=False,
        ):
            st.code(result_str[:4000], language="json")
    elif kind == "tool_error":
        st.error(f"Tool `{event['name']}` failed: {event['error']}")
    elif kind == "done":
        u = event["usage"]
        st.caption(
            f"✅ Completed in {event['iterations']} iteration(s). "
            f"Tokens — input: {u.input_tokens}, output: {u.output_tokens}, "
            f"cache_read: {u.cache_read_input_tokens}"
        )


def main() -> None:
    init_state()

    with st.sidebar:
        st.header("About")
        st.markdown(
            "Ask questions about a synthetic PE portfolio:\n\n"
            "- **Fund I** — 2018 vintage, harvesting\n"
            "- **Fund II** — 2022 vintage, investing\n"
            "- **Fund III** — 2026 vintage, just deployed\n"
        )
        st.markdown("---")
        st.subheader("Try asking…")
        for q in [
            "Give me a one-paragraph health check on the portfolio.",
            "Which fund needs the most attention right now?",
            "If Fund I sells the remaining NAV at marked value, what does the GP earn in carry?",
            "What does Fund III's LPA say about AI governance?",
            "Compare management fees across all three funds.",
        ]:
            if st.button(q, use_container_width=True):
                st.session_state.queued_question = q
                st.rerun()
        st.markdown("---")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.history = []
            st.session_state.agent_messages = []
            st.rerun()

    for turn in st.session_state.history:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user":
                st.markdown(turn["content"])
            else:
                for event in turn["events"]:
                    render_event(event)

    queued = st.session_state.pop("queued_question", None)
    prompt = queued or st.chat_input("Ask about the portfolio…")
    if prompt:
        st.session_state.history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            events: list[dict] = []
            container = st.container()
            with container:
                with st.spinner("Thinking…"):
                    for event in run_agent_streaming(prompt):
                        events.append(event)
                        render_event(event)
            st.session_state.history.append({"role": "assistant", "events": events})


if __name__ == "__main__":
    main()
