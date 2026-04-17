# moyan benchmark

衡量 `moyan` 插件究竟能减少多少 Claude 输出 token，以及在**哪些真实开发场景**下有效、哪些场景反而丢信息。

## 设计原则

1. **基线是"中文 normal"，不是英文。** 对比 `D_moyan_jing` vs `B_zh_normal`，隔离"讲中文"和"莫言"两个效应。
2. **从玩具到真实。** 4 层场景（L1 玩具 / L2 常见 / L3 真实代码 + trace / L4 长程 commit+review+破坏性操作）。
3. **配对统计。** 每个 prompt 在所有组下都跑，Δ 按 prompt 配对算，用 Wilcoxon + 95% bootstrap CI。
4. **质量护栏。** 第二个 Claude 盲评技术完整度；Δ 不与质量挂钩就是假胜利。
5. **Trace 全留。** 每次调用的输入/输出/usage/分析落盘 JSON，为后续 SKILL.md 优化铺路。

## 5 个对照组

| 代号 | 含义 | 系统 prompt |
|---|---|---|
| `A_en_normal` | 英文 normal（参考） | `You are Claude, a helpful coding assistant.` |
| **`B_zh_normal`** | **中文 normal（主基线）** | 同上 + "Reply in Chinese" |
| `C_moyan_jian` | 莫言 简 | SKILL.md 全文 + `[当前级别 简]` |
| `D_moyan_jing` | 莫言 精（默认） | 同上，级别 精 |
| `E_moyan_wenyan` | 莫言 文言文 | 同上，级别 文言文 |

## Prompt 集（52 条）

| 类别 | 数量 | 期望行为 |
|---|---|---|
| `explain`（L1） | 8 | 省字 |
| `debug`（L2/L3） | 20 | 省字 |
| `howto`（L2） | 6 | 省字 |
| `review`（L4） | 4 | 省字，一行一条 |
| `commit`（L4） | 4 | **不套级别**，遵 Conventional Commits |
| `codegen`（L1/L2/L3） | 5 | **代码块不压缩**（guard check） |
| `destructive`（L4） | 2 | **触发 Auto-Clarity**（出现「警告」） |
| `multiturn`（L2/L3） | 3 | 测"持续生效" |

## 使用

```bash
# 1. 装依赖
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 2. 冒烟（5 prompt × 2 组 × 1 seed ≈ $0.02）
python run.py --run-id smoke --groups B_zh_normal,D_moyan_jing --limit 5 --samples 1

# 3. 精简（30 prompt × 5 组 × 2 seed，单模型 ≈ $3–5）
python run.py --run-id v1 --models claude-sonnet-4-6 --limit 30 --samples 2
python judge.py --run-id v1
python analyze.py --run-id v1
python attribute.py --run-id v1

# 4. 全量（52 prompt × 5 组 × 3 seed × 2 模型 ≈ $40–60）
python run.py --run-id full --models claude-opus-4-7,claude-sonnet-4-6 --samples 3
python judge.py --run-id full --judge-model claude-sonnet-4-6
python analyze.py --run-id full
python attribute.py --run-id full
```

## 产出

每次 `--run-id` 得到：

```
traces/{run_id}/
  {prompt_id}__{group}__seed{n}[_t{turn}].json   # 原始 trace
  _judgments/*.json                              # 盲评结果

results/{run_id}/
  metrics.csv                 # 每条 trace 一行
  per_prompt.csv              # 配对：baseline vs 每个 moyan 组
  summary.csv                 # 按 (model, group)
  by_layer.csv                # 按 (model, group, layer)
  by_category.csv             # 按 (model, group, category)
  guard_findings.csv          # 边界行为违规（代码被压、警告缺失）
  report.md                   # 人读报告
  attribution.md              # 短语归因 + 回归候选
```

## Trace schema（节选）

```json
{
  "prompt_id": "L2-debug-01-useeffect-loop",
  "group": "D_moyan_jing",
  "model": "claude-sonnet-4-6",
  "seed": 0,
  "usage": { "input_tokens": 1823, "cache_read_input_tokens": 1750, "output_tokens": 412 },
  "analysis": {
    "char_count": 380,
    "code_block_chars": 120,
    "non_code_chars": 260,
    "filler_hits": { "客套": 0, "填词": 1, "铺垫": 0, "犹豫": 2, "自指": 0 },
    "contains_warning": false,
    "script_simplified_ratio": 1.0
  },
  "response": "...",
  "system_prompt": "...",
  "turns": [...]
}
```

## 统计方法

- **配对 Δ**：`delta_out = 1 - moyan_out / baseline_out`，按 (prompt, model, moyan_group) 配对
- **区间**：95% bootstrap CI（1000 次重抽样）
- **显著性**：Wilcoxon signed-rank（非参、配对，H1: Δ > 0）
- **分层**：(model × group × layer)、(model × group × category) 独立报告

## 已知局限

- SKILL.md 注入吃 ~2k input token；只有 prompt caching 命中时才真省（长会话更划算）
- LLM-as-judge 有系统性偏差——建议抽 20% 人工复核
- `temperature=0` 不等于确定性；用 `--samples 3` 取均值
- L4 多轮场景只有 3 个——想要真实长程结论需要扩展
- 只测 API 直连；未测 Claude Code CLI 内 skill 加载路径（集成测试是 v2）

## 下一步（v2）

- [ ] 接入 Claude Code / Agent SDK 作集成测试层
- [ ] 扩展 multi-turn 到 10 条真对话
- [ ] 人工复核 20% judgments，算 Cohen's κ
- [ ] 成本-收益曲线：Δ × 调用量 × 价格 → 实际月省多少
