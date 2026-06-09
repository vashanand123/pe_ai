"""Phase 7 — Skills demonstration.

A skill is a chunk of instructions that gets loaded into Claude's context
ONLY when relevant. The skill's `description` (in its frontmatter) is what
Claude reads to decide whether the skill applies; if it does, Claude then
reads the full body.

This demo loads .claude/skills/fund-cfo-style/SKILL.md, parses out its
description and body, and prepends the body to a Claude API call's system
prompt. Same question is asked WITH and WITHOUT the skill so you can see
the formatting / voice difference.

In Claude Code or Claude Desktop, this loading is automatic — drop the
SKILL.md in .claude/skills/<name>/ and Claude loads it when relevant.

Run from the pe_ai/ directory:
    uv run python phase7/skill_demo.py
"""

import os
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = PROJECT_ROOT / ".claude" / "skills" / "fund-cfo-style" / "SKILL.md"
MODEL = "claude-opus-4-7"

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")


def load_skill(path: Path) -> tuple[str, str, str]:
    """Return (name, description, body) parsed from a SKILL.md file."""
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, flags=re.DOTALL)
    if not fm_match:
        raise ValueError(f"No YAML frontmatter found in {path}")
    fm = fm_match.group(1)
    body = fm_match.group(2).strip()
    name = re.search(r"^name:\s*(.+)$", fm, flags=re.MULTILINE).group(1).strip()
    desc = re.search(r"^description:\s*(.+)$", fm, flags=re.MULTILINE | re.DOTALL).group(1).strip()
    return name, desc, body


def ask_with_skill(client: anthropic.Anthropic, question: str, skill_body: str | None) -> None:
    base_prompt = (
        "You are a senior analyst at a private fund management platform. "
        "Answer the user's question accurately based on the data provided."
    )
    system = base_prompt
    if skill_body:
        system = base_prompt + "\n\n" + skill_body

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    print(text)
    print(f"\n[tokens — input: {response.usage.input_tokens}, output: {response.usage.output_tokens}]\n")


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    name, description, body = load_skill(SKILL_PATH)
    print(f"Loaded skill: {name}")
    print(f"Description ({len(description)} chars):")
    print(f"  {description[:200]}...\n")
    print(f"Body ({len(body)} chars)")
    print("=" * 72)

    client = anthropic.Anthropic()

    question = (
        "Here are the three funds we manage:\n\n"
        "Fund I — 2018 Buyout, harvesting. Committed $300M, called $300M, "
        "distributed $420M, NAV $60M.\n"
        "Fund II — 2022 Buyout, investing. Committed $500M, called $310M, "
        "distributed $30M, NAV $340M.\n"
        "Fund III — 2026 Buyout, investing. Committed $750M, called $80M, "
        "distributed $0M, NAV $80M.\n\n"
        "Give me a one-paragraph health check across all three."
    )

    print("\n" + "=" * 72)
    print("WITHOUT skill (just base system prompt)")
    print("-" * 72)
    ask_with_skill(client, question, skill_body=None)

    print("=" * 72)
    print("WITH fund-cfo-style skill loaded")
    print("-" * 72)
    ask_with_skill(client, question, skill_body=body)


if __name__ == "__main__":
    main()
