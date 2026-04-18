"""Shared infra: experimental groups, system prompts, trace schema, API client."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "skills" / "moyan" / "SKILL.md"
BENCH_ROOT = Path(__file__).resolve().parent


def load_skill_body() -> str:
    """SKILL.md without YAML frontmatter — frontmatter is plugin metadata, not model input."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    if text.startswith("---"):
        _, _, rest = text.partition("\n---\n")
        return rest.strip()
    return text.strip()


# 5 groups. B (Chinese normal) is the primary baseline — moyan savings
# must be measured vs B, not A, to isolate the "莫言" effect from "use Chinese".

SKILL_BODY = load_skill_body()

BASELINE_ZH = "You are Claude, a helpful coding assistant. Reply in Chinese (Simplified)."
BASELINE_EN = "You are Claude, a helpful coding assistant."


def moyan_system(level: str) -> str:
    """level: 简 / 精 / 文言文"""
    return (
        "You are Claude, a helpful coding assistant. The following skill is active "
        "for this session:\n\n"
        "---\n"
        f"{SKILL_BODY}\n"
        "---\n\n"
        f"[当前莫言状态: 已启动 · 级别 {level} · 字形随用户输入]"
    )


GROUPS: dict[str, dict[str, Any]] = {
    "A_en_normal": {
        "label": "英文 normal",
        "system": BASELINE_EN,
        "uses_skill": False,
        "level": None,
    },
    "B_zh_normal": {
        "label": "中文 normal (baseline)",
        "system": BASELINE_ZH,
        "uses_skill": False,
        "level": None,
    },
    "C_moyan_jian": {
        "label": "莫言 简",
        "system": moyan_system("简"),
        "uses_skill": True,
        "level": "简",
    },
    "D_moyan_jing": {
        "label": "莫言 精 (默认)",
        "system": moyan_system("精"),
        "uses_skill": True,
        "level": "精",
    },
    "E_moyan_wenyan": {
        "label": "莫言 文言文",
        "system": moyan_system("文言文"),
        "uses_skill": True,
        "level": "文言文",
    },
}

BASELINE_GROUP = "B_zh_normal"
MOYAN_GROUPS = ["C_moyan_jian", "D_moyan_jing", "E_moyan_wenyan"]


# ---------- Trace schema ----------

@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class Analysis:
    has_code_block: bool = False
    filler_hits: dict[str, int] = field(default_factory=dict)
    contains_warning: bool = False


@dataclass
class Trace:
    prompt_id: str
    layer: str
    category: str
    group: str
    model: str
    seed: int
    timestamp: float
    latency_ms: int
    system_prompt: str
    turns: list[dict]
    response: str
    usage: Usage
    analysis: Analysis
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- Text analysis ----------

# Filler phrases the skill says to strip. Counted in non-code text only,
# surfaced in trace JSON to help the agent spot regressions.
FILLER_PATTERNS: dict[str, list[str]] = {
    "客套": ["好的", "当然可以", "没问题", "乐意帮您", "很高兴", "希望这能帮到您"],
    "填词": ["其实", "基本上", "实际上", "就是说", "也就是说"],
    "铺垫": ["接下来我将", "让我来", "首先让我", "我来帮你分析一下", "我先解释一下"],
    "犹豫": ["可能", "或许", "也许", "大概", "应该是"],
    "自指": ["我注意到", "我看到", "我觉得", "在我看来"],
}

WARNING_MARKERS = ["警告", "⚠", "注意：", "不可逆", "永久", "DANGER", "WARNING"]

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)


def analyze_response(text: str) -> Analysis:
    a = Analysis()
    a.has_code_block = "```" in text
    non_code = _CODE_FENCE.sub("", text)
    a.filler_hits = {cat: sum(non_code.count(p) for p in phrases)
                     for cat, phrases in FILLER_PATTERNS.items()}
    a.contains_warning = any(m in text for m in WARNING_MARKERS)
    return a


# ---------- Trace IO ----------

def trace_path(run_id: str, prompt_id: str, group: str, seed: int, turn: int = 0) -> Path:
    d = BENCH_ROOT / "traces" / run_id
    d.mkdir(parents=True, exist_ok=True)
    suffix = f"_t{turn}" if turn else ""
    return d / f"{prompt_id}__{group}__seed{seed}{suffix}.json"


def save_trace(run_id: str, trace: Trace, turn: int = 0) -> Path:
    p = trace_path(run_id, trace.prompt_id, trace.group, trace.seed, turn)
    p.write_text(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def load_prompts() -> list[dict]:
    with (BENCH_ROOT / "prompts.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------- API client ----------

def call_claude(
    *,
    client,
    model: str,
    system_prompt: str,
    turns: list[dict],
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> tuple[str, Usage, int]:
    """Returns (text, usage, latency_ms). System prompt is cached (ephemeral)."""
    system = [{"type": "text", "text": system_prompt,
               "cache_control": {"type": "ephemeral"}}]
    t0 = time.time()
    resp = client.messages.create(
        model=model,
        system=system,
        messages=turns,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    latency_ms = int((time.time() - t0) * 1000)
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    u = resp.usage
    usage = Usage(
        input_tokens=getattr(u, "input_tokens", 0),
        output_tokens=getattr(u, "output_tokens", 0),
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
    )
    return text, usage, latency_ms


def get_client():
    from anthropic import Anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    return Anthropic(api_key=key)
