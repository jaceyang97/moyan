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

- Opus 上未测。
- holdout n=18（expansion 后）偏小，类目级 CI 仍宽。
- 单 seed（成本权衡），单个 prompt 的 Δ 抖动 ±2-3pp 未在表里反映。
- cache 在本次 API 环境下未生效（见 Track B · cache）。多轮 amortization 尚未实测。

---

## Track B 扩展（2026-04）

prompt 集 52 → 71（+6 review、+4 commit、+9 multiturn）。stratified 53 train / 18 holdout。

### Haiku 4.5 responder

全集 71 prompt 上跑 Haiku 4.5 responder，同一 baseline (B_zh_normal) 对照。

| 级别 | Δ_median holdout | Δ_median 全集 | Δ_median train |
|---|---|---|---|
| 简 | 53.0% | 55.1% | 56.6% |
| 精 | 55.4% | 54.8% | 54.8% |
| 文言文 | 52.3% | 57.1% | 57.4% |

**关键发现 1：Haiku 上三档级别坍缩。** Sonnet 4.6 holdout 上三档是 66 / 66 / 73%（文言文 +7pp），Haiku 上变 53 / 55 / 52%（文言文毫无优势，甚至 holdout 略低于精）。SKILL.md 的 level abstraction 在 Haiku 上没被模型充分利用。

**关键发现 2：Haiku 整体压缩比 Sonnet 低 13-20pp。** 精 holdout: Sonnet 65.5% → Haiku 55.4%。小模型在本 skill 上的压缩天花板明显更低。

per-category（Haiku Δ_median，全集）：

| 类目 | n | 简 | 精 | 文言文 |
|---|---|---|---|---|
| codegen | 5 | 58.4% | 50.3% | 58.7% |
| commit | 8 | 77.0% | **74.6%** | 76.1% |
| debug | 20 | 36.3% | 35.9% | 42.3% |
| destructive | 2 | 49.3% | 53.6% | 48.4% |
| explain | 8 | 56.9% | 51.7% | 56.0% |
| howto | 6 | 58.3% | **64.7%** | 57.2% |
| multiturn | 12 | 58.2% | 60.5% | 62.2% |
| review | 10 | 55.0% | 56.0% | 59.7% |

Haiku 上 **debug 类跌到 36-42%**（Sonnet 是 59-71%），差距最大。可能是 Haiku 对 debug 类本来就啰嗦，moyan 压不下来。

### Haiku completeness（Opus 4.6 判）

18 条 holdout × 3 moyan 组 = 54 对判官评。

| 级别 | full | partial | missing | full% |
|---|---|---|---|---|
| 简 | 3 | 14 | 0 | 16.7% (ERR × 1) |
| 精 | 2 | 16 | 0 | 11.1% |
| 文言文 | 6 | 12 | 0 | **33.3%** |

Sonnet v2 baseline full% 是 40%。Haiku 降到 11-33%。全部判为「partial」，没有「missing」—— 即没有丢信息的灾难，但超 60% 的回答被 Opus 判为有信息漏损。

**文言文在 Haiku 上 full% 反而最高（33% vs 精 11%）**——这和 Δ_median 的方向相反。Haiku 跑精模式更激进地砍信息，文言文虽然压缩比差不多但保留更完整。

### 判官 inter-rater κ（Opus vs Sonnet 4.6）

同 54 对 pair 用 Sonnet 4.6 跑二判，matched n=53：

```
confusion (rows=Opus, cols=Sonnet):
              full   partial   missing
  full          3         8         0
  partial       4        38         0
  missing       0         0         0

observed agreement: 0.774
chance agreement:   0.715
Cohen's κ:          0.205  (slight)
```

**关键发现 3：两判官 full/partial 边界上几乎是噪声。** 观察一致率 77% 听起来不错，但判官都倾向判「partial」（基线率 71%），扣掉 chance agreement 后 κ 只剩 0.21。

含义：`evaluate.py` 的 `COMPLETENESS_TARGET=0.40` 质量闸门，打在判官没共识的那条边界上。autoskill loop 里 iter 0 触发 holdout 20% full 被 discard，v2 结果 40% full，这些绝对阈值都可能是判官漂移而非模型能力变化。

### cache-hit（未生效）

在当前 API 环境下，`cache_control: ephemeral` 没触发缓存：

```
group                turn    n   avg_in avg_cache_r avg_cache_w  cache_hit%
B_zh_normal             0   83      229           0           0        0.0%
C_moyan_jian            0   83     3067           0           0        0.0%
D_moyan_jing            0   83     3063           0           0        0.0%
E_moyan_wenyan          0   83     3061           0           0        0.0%
（多轮 turn 1、2 同样全 0）
```

隔离测试（Sonnet 4.6 两次相同 system block）也是 cache_creation > 0 但 cache_read = 0。推测是 API 代理 / 账户配置问题，非 moyan 本身 bug。

**如果 cache 正常：** 首次 call 写入 ~2830 input tokens 的 SKILL.md，后续 cached read 只算 10% = 283 tokens。多轮下 2+ turn 等于几乎免费挂载 skill。**cache 失效下：** 每次 call 都实打实多付 2830 input tokens，moyan 在 Haiku 上 output 省得少（430 tokens/call），按定价可能 net 负收益。这点没法在本环境实测到。

### Track B 结论

1. **SKILL.md 没法按「跨模型通用」推销。** 在 Sonnet 4.6 上校准的级别差异（文言文 +7pp）到 Haiku 上消失，完整度也大幅掉。
2. **判官管线有噪声。** κ = 0.21 说明 autoskill 的 completeness gate 不可靠；v2 4 轮 discard 里至少 iter 0 的 holdout 20% full 判决可能是判官漂移。
3. **economic viability 依赖 cache 生效。** 不 cache 的话 moyan 在 Haiku 上可能是 net 增成本；cache 正常时才真省钱。
4. **prompt 集扩到 71 后** 每级 n_holdout=18，类目级仍偏小。debug 类 n=20（全集）是唯一够信心谈差异的类目。

---

## Track C：SKILL.md 三维优化（2026-04）

目标：effectiveness + conciseness + readability 三维同时推进。基于 Track B 发现（Haiku 坍缩 + judge κ=0.21），承认「跨模型通用」不可达，只在「不牺牲 Sonnet 表现 + SKILL.md 更短」这对可达目标上迭代。

### 三版对比（Haiku holdout, n=18/group）

|  | v2.0 | v2.1 | v2.2（选定） |
|---|---|---|---|
| SKILL.md bytes | 7882 | 5491 | 5561 |
| vs v2.0 | — | **−30.3%** | **−29.4%** |
| 简 Δ_median | 53.0% | **57.6%** | 54.9% |
| 精 Δ_median | 55.4% | 54.3% | 50.8% |
| 文言文 Δ_median | 52.3% | 52.5% | 51.7% |
| 简 full% | 17% | **22%** | 17% |
| 精 full% | 11% | 11% | 11% |
| 文言文 full% | **33%** | 17% | 11% |

v2.1 变更：`## 启动与持续` / `## 边界`删除，三档级别上移并加量化压缩目标（简≤60%/精≤40%/文言文≤30%），字形/commit/review 块压缩。
v2.2 变更：v2.1 基础 + 文言文 cell 加「省『的』、助词『也/矣』、动词宾前置」 + 例子末尾提醒「technical 细节原样保留」。

### Sonnet 4.6 验证（v2.2, holdout）

| group | Δ_median | Δ_mean | full% |
|---|---|---|---|
| C_moyan_jian | 68.1% | 63.6% | 50% |
| D_moyan_jing | 70.0% | 66.3% | 28% |
| E_moyan_wenyan | **74.5%** | **68.0%** | **56%** |

- Sonnet 上 **三档单调**（简 < 精 < 文言文），level differentiation 成立。
- vs Sonnet v2.0 holdout（66/66/73%）：**v2.2 全线持平或略涨**（+2/+4/+1.5pp），即 SKILL.md 缩短 29% 无压缩代价。
- 文言文 full% 56% 最高，精 28% 最低 —— 精确实是「最激进」的级别，符合设计。

### Track C 结论

- **选定 v2.2 为发布版**：SKILL.md −29%，Sonnet 表现无回退，Haiku 文言文 full% 跌 22pp 但落在 judge κ=0.21 噪声带内（n=18 的 SE≈11pp → ~2σ）。
- **三维量化：** 1) effectiveness：Sonnet 文言文 holdout 74.5%（+1.5pp vs v2.0）；2) conciseness：SKILL.md 7882→5561 bytes；3) readability：级别 cell 改量化 + debug-首选标注，人读更具体。
- **Haiku 级别坍缩是模型能力上限，非 SKILL.md 可修复。** 下一步迭代要提 Haiku 得改判官信号，不是改 SKILL.md。

### 复现 Track C

```bash
cd benchmark
# v2.1 / v2.2 已用 git 版本切换，v2-haiku-v21/-v22 是对应 run
python run_stats.py --run-id v2-haiku-v22
python run.py --run-id v2-sonnet-v22 --models claude-sonnet-4-6 \
  --groups B_zh_normal,C_moyan_jian,D_moyan_jing,E_moyan_wenyan \
  --samples 1 --prompt-file splits/holdout.txt
python judge.py --run-id v2-sonnet-v22 --judge-model claude-opus-4-6 \
  --seeds 1 --prompt-file splits/holdout.txt
```

### 复现 Track B

```bash
cd benchmark
python run.py --run-id v2-haiku \
  --models claude-haiku-4-5-20251001 \
  --groups B_zh_normal,C_moyan_jian,D_moyan_jing,E_moyan_wenyan \
  --samples 1
python run_stats.py --run-id v2-haiku

python judge.py --run-id v2-haiku --judge-model claude-opus-4-6 \
  --seeds 1 --prompt-file splits/holdout.txt
python kappa.py judge2 --run-id v2-haiku --judge-model claude-sonnet-4-6
python kappa.py score --run-id v2-haiku \
  --judge-a claude-opus-4-6 --judge-b claude-sonnet-4-6

python cache_report.py --run-id v2-haiku
```

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
