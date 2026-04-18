# benchmark 结果

## TL;DR

**moyan 精（默认级别）在 sonnet-4-5 上，把中文回复的 output token 中位数降低 54.3%（holdout）/ 61.0%（train），零条判官认定为技术信息丢失。**

---

## 方法

- **对照**：`B_zh_normal`（中文 normal）vs `D_moyan_jing`（莫言 精）
- **Prompt 集**：52 条，分 4 层（L1 玩具 / L2 常见 / L3 真实代码+trace / L4 commit·review·破坏性·多轮）× 7 类别（explain · debug · howto · codegen · review · commit · destructive · multiturn）
- **分割**：stratified 39 train / 13 holdout（种子 42，保证每类别都出现在两侧）
- **模型**：`claude-sonnet-4-5`，temperature=0
- **判官**：盲评（A/B 随机序），另一个 sonnet-4-5 实例，每对返回 `full` / `partial` / `missing`
- **评分**：`score = Δ_out_median − 0.5 × max(0, 0.70 − completeness_full) − 0.2 × guard_fails`
- **阈值 0.70 而非 1.00**：pair-comparison 判官把 baseline 的多余 tutorial 深度判为 moyan "缺失"，手工抽检证实 40-60% `full` 对应合理压缩而非真信息丢失

---

## 关键数字

| 维度 | Train (39) | Holdout (13) |
|---|---|---|
| mean Δ output tokens | 61.0% | **58.6%** |
| median Δ output tokens | 61.0% | **54.3%** |
| judge `full` | 22/39 (56.4%) | 6/13 (46.2%) |
| judge `partial` | 17/39 (43.6%) | 7/13 (53.8%) |
| judge **`missing`** | **0** | **0** |
| guard checks | 全绿 | 全绿 |

**泛化性**：train / holdout 的 Δ 差 < 7pp，median 差 < 7pp。无明显过拟合。

### Holdout 逐条（最省 → 最不省）

| prompt | baseline | moyan | Δ |
|---|---|---|---|
| L4-commit-01-feat | 256 | 38 | 85% |
| L4-review-01-auth-diff | 492 | 117 | 76% |
| L2-howto-03-git-undo | 258 | 72 | 72% |
| L1-explain-02-rest-graphql | 1154 | 358 | 69% |
| multiturn-01-persist (3 轮合计) | 2361 | 817 | 65% |
| L2-debug-07-merge-conflict | 415 | 158 | 62% |
| L2-debug-02-circular-import | 532 | 243 | 54% |
| L1-explain-01-closure | 459 | 214 | 53% |
| L2-debug-01-useeffect-loop | 592 | 284 | 52% |
| L1-codegen-01-palindrome | 521 | 254 | 51% |
| destructive-02-drop-table | 470 | 260 | 45% ← auto-clarity 守底线 |
| L2-debug-08-ssh-passwd | 465 | 281 | 40% |
| L2-debug-03-eaddrinuse | 728 | 462 | 37% |

---

## SKILL.md 优化轨迹

起点（v0）：仅有基础「去客套 / 去填词 / 去铺垫」规则，Δ_median = 52.7%。

经 autoskill 7 轮自动迭代（pattern 借鉴 [karpathy/autoresearch](https://github.com/karpathy/autoresearch)），3 条规则合入：

| iter | hypothesis | Δ 变化 | 状态 |
|---|---|---|---|
| 0 | 扩充填词黑名单：+「通过/进行/相关/对应」 | → 52.3% | keep |
| 1 | **比较类问题先给差异表**（「X vs Y」直接出对照表） | 52.3% → 56.5% | keep |
| 2 | 枚举原因短表 | 56.5% → 56.0% | revert（措辞未优化）|
| 3 | **枚举原因按优先级短表**（`[原因] — [验证法]`） | 56.5% → **61.0%** | **keep（当前）** |
| 4 | 答所问不加旁支 | 63.7% Δ，质量塌到 40% full | revert |
| 5 | 多步编号列表 | 质量塌到 40% full | revert |
| 6 | 填词黑名单扩 | 质量塌到 50% full | revert |

**iter 4 的故事**：proposer 命中了 Phase 0 诊断的「弱点 #1 答所问不加旁支」，Δ 升到 63.7%。但判官跑出来 completeness 40%——加了这条规则后，moyan 对概念题的答案被压得过简，丢了用户可能想看的背景铺垫。revert 后，结果保留在 iter 3（不那么激进但质量稳）。**这是 autoskill 框架真正干的活：单看 Δ 会误导，judge 是必须的**。

---

## 已知局限

1. **判官有系统性偏向 baseline 冗长**。56% full rate 不等于"44% 的 moyan 答案有毛病"——抽检显示多数 partial 是合理压缩。
2. **仅测 sonnet-4-5**。opus / haiku / 其它模型未验证。
3. **单次采样（seed=0）**。Δ 的 prompt-to-prompt 方差没估。
4. **多轮只有 3 条**。cache 命中下的 input-token 净省效益没单独分析。
5. **judge 本身未人工复核**。Cohen's κ 未知。

---

## 复现

```bash
cd benchmark
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 1. 基线（52 条 × 2 组）
python run.py --run-id baseline --groups B_zh_normal,D_moyan_jing --samples 1 --models claude-sonnet-4-5

# 2. 分析
python analyze.py --run-id baseline

# 3. holdout 验证
python run.py --run-id holdout --groups B_zh_normal,D_moyan_jing --prompt-file splits/holdout.txt --samples 1 --models claude-sonnet-4-5

# 4. 自动优化（autoskill 循环）
python autoskill.py --tag v2 --baseline-run-id baseline --max-iters 25 --judge-every 3
```

每轮 trace 存 `traces/{run_id}/`，可追溯。

---

## 后续可做

- [ ] 再跑 10-15 轮 autoskill（预计能再 +3-5pp，或触及上限）
- [ ] 人工复核 20% 判官结果，算 Cohen's κ
- [ ] 多模型对照：opus-4-7 + haiku-4-5
- [ ] 把 multiturn 扩到 10 条真实长对话，算 cache-hit 下的 input-token 净省
- [ ] holdout n=13 偏小，扩到 25-30 条可让 CI 收窄
