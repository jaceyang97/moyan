# benchmark 结果 v2（Sonnet 4.6 · Opus 4.6 judge）

> v1 结果（Sonnet 4.5 时代）见 [`RESULTS.md`](RESULTS.md)。
> v2 实时迭代日志见 [`results.tsv`](results.tsv)。

## TL;DR

**在 Sonnet 4.6 上，moyan 三档级别中位 token 节省率：**

| 级别 | Δ_median (holdout) | Δ_mean (holdout) | Δ_median (train) | 适用 |
|---|---|---|---|---|
| **简** | 66.1% | 62.7% | 63.6% | 正式文档、对外沟通 |
| **精**（默认）| 65.5% | 67.1% | 65.8% | 日常开发问答 |
| **文言文** | **73.0%** | **70.6%** | **70.6%** | 极省 token，debug/explain 类首选 |

**文言文 在最难压缩的类目（debug / explain / howto）反超 精 8-12pp。** 文言文不是审美点缀，是真正的高压缩模式。

---

## 方法

- **对照基线**：`B_zh_normal`（中文 normal）
- **3 个 moyan 组**：`C_moyan_jian`（简）/ `D_moyan_jing`（精）/ `E_moyan_wenyan`（文言文）
- **52 条 prompt**，stratified 39 train / 13 holdout（种子 42）
- **响应模型**：`claude-sonnet-4-6`，temperature=0
- **判官**（仅 iter 评估时启用）：`claude-opus-4-6`
- **n=1 seed**（成本权衡；autoskill iter 内部用 n=2）

---

## 全量结果

### 顶层（n=50 配对 prompt，跨 train+holdout）

| 级别 | n | Δ_median | Δ_mean | 总输入 token | 总输出 token |
|---|---|---|---|---|---|
| 简 | 50 | 63.8% | 62.7% | 51,129 | 18,348 |
| 精 | 52 | 65.8% | 67.5% | 65,101 | 20,044 |
| 文言文 | 50 | 70.7% | 70.1% | 51,129 | 14,580 |

文言文绝对输出 token 比 精 少 27%（14,580 vs 20,044）。

### 按类目分（Δ_median）

| 类目 | n | 简 | 精 | 文言文 | 文言文 Δ vs 精 |
|---|---|---|---|---|---|
| codegen | 5 | 83.9% | 84.6% | 84.3% | 持平（饱和）|
| commit | 4 | 74.2% | **82.0%** | 73.3% | **−8.7pp** ⚠ |
| **debug** | 10 | 60.3% | 59.1% | **71.2%** | **+12.1pp** 🏆 |
| **explain** | 8 | 65.1% | 64.1% | **72.7%** | **+8.6pp** |
| **howto** | 6 | 64.1% | 61.7% | **72.0%** | **+10.3pp** |
| real (L3 长 trace) | 10 | 63.2% | 69.1% | 69.1% | 持平 |
| review | 4 | 53.1% | 59.3% | 57.8% | −1.5pp |
| explain/debug L1-L2 | 7 | 58-78% | 67-79% | 63-77% | 混合 |

**关键观察：** 精 在「内容承载多」的硬类目（debug 59%、review 59%）撞到地板。文言文跨过这个地板（debug 71%）—— 因为文言文本身的语法压缩性（无 的/了/着，介词少，倒装允许）叠加在 moyan 的规则之上。

**例外：commit 不要用文言文。** Conventional Commits 格式需要英文关键字（feat/fix/refactor），文言文风格反而拖长。SKILL.md 里 `## 写 commit 时` 一节强制套 Conventional Commits 不走级别压缩，所以这个类目正常用户不会触发问题。

---

## 与 v1 对比

| 维度 | v1（Sonnet 4.5 + Sonnet judge）| v2（Sonnet 4.6 + Opus judge）|
|---|---|---|
| 精 Δ_median (holdout) | 54.3% | 65.5% (+11pp) |
| 精 Δ_mean (holdout) | 58.6% | 67.1% (+8.5pp) |
| 判官 baseline completeness_full | 56% | 40% |
| 文言文测过吗 | 否 | **是** |

精的 +11pp 提升一部分来自 Sonnet 4.6 对压缩信号更敏感，一部分来自判官口径变化（Opus 4.6 比 Sonnet 4.5 更严，所以分数公式里的 0.70 阈值在 v2 重新校准为 0.40）。

文言文 73.0% 是 v2 全新数字 —— v1 没有跑过这个级别。

---

## autoskill v2 迭代记录（4 轮全 discard）

| iter | hypothesis | train Δ vs baseline | holdout completeness | decision |
|---|---|---|---|---|
| 0 | 加「枚举解法短表」规则 | +2.01pp | 40% → **20%** | discard:holdout-overfit |
| 1 | 扩「留」规则覆盖范围 | +0.11pp | (skip) | discard（未过阈值）|
| 2 | 紧三档级别表自身的描述（subtractive）| +0.55pp | (skip) | discard |
| 3 | 换 worked example 为 debug 类（radical）| **−2.7pp** | (skip) | discard |

**结论：当前 SKILL.md 在 Sonnet 4.6 上处于强局部最优。** 单条编辑级别的扰动落在噪声地板内（±2pp 抖动）；新增结构会冲坏 completeness（iter 0）；换 example 反而拖低（iter 3，可能是连接池 example 在锚定 explain 类的压缩）。

**autoskill 框架本身有效**：
- 4 轮里 1 轮（iter 0）触发了 holdout-overfit 守护门 —— 正是为了 v1-iter-4 那种「训练涨、留存度崩」场景设计的
- 1 轮（iter 3）触发了 train 阈值守护 —— 即使 radical 改动，也没被强行 keep
- 0 轮 false-keep（错误地保留了坏改动）

总成本：~$5–7（baseline + 4 iters + 简/文言文全量评测）。

---

## 已知局限

- 仅在 Sonnet 4.6 上验证。Opus / Haiku 未测。
- judge 只跑了 baseline holdout（10 条）+ iter 0 holdout（10 条），不是全集。Cohen's κ 未算。
- holdout n=13 偏小，类目级 CI 较宽。
- 单 seed（成本权衡），单个 prompt 的 Δ 抖动 ±2-3pp 未在表里反映。
- 多轮 prompt 仅 3 条，cache-hit 下的实际省 token 收益没单独算。

---

## 复现

```bash
cd benchmark
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 1. baseline（B + 3 moyan 组，全 52 prompt）
python run.py --run-id v0 \
  --groups B_zh_normal,C_moyan_jian,D_moyan_jing,E_moyan_wenyan \
  --models claude-sonnet-4-6 \
  --samples 1

# 2. 上面的脚本算 per-level Δ — 见 results 计算器（README 引用）
# 3. autoskill 迭代（agent-as-loop）：用 Claude Code Opus 4.6 跑
#    > Read benchmark/program.md and run the autoskill loop for 25 iterations.
```

---

## 后续可做

- 跑 Haiku 4.5 看小模型是否对压缩规则响应更强
- 扩 multiturn prompt 到 10 条，算 cache-hit 下的 input-token 净省
- 人工复核 20% Opus 判官结果，算 Cohen's κ，验证 0.40 baseline 是判官真的严还是模型真的丢信息
- 判官切到不同 family（如 GPT-4o）做 cross-check
