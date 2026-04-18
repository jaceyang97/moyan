# 莫言 · moyan

> 少言多意。中文省 token 模式 · Claude Code plugin。

受 [caveman](https://github.com/JuliusBrussee/caveman) 启发。Caveman 以"山顶洞人"的英语省 token，**莫言** 以简洁中文省 token —— 回复少而准，字字算数。

- **白话两档**：简 / 精（默认）
- **文言文**：最省字，古雅
- **简繁通吃**：自动跟随用户输入，或手动切换
- **Claude Code only**（目前）

## 究竟省多少？

在 52 条编程问答（概念解释 / 调试 / 代码审查 / commit / 多轮对话等）上测 `claude-sonnet-4-5`：

- **output token 中位数降 54% / 均值降 59%**（holdout 13 条）
- **0 条判官认定为技术信息丢失**
- commit / review / auto-clarity 等边界行为全守住

详见 [`benchmark/RESULTS.md`](benchmark/RESULTS.md)。benchmark 可复现（52 条 prompt + run/judge/analyze 脚本全在 `benchmark/`）。

## 看一眼差别

输入：「为什么我这条 SQL 查询越来越慢？」

| 模式 | 回复 |
|------|------|
| 原始 | 随着数据量增长，查询变慢通常有几个原因。首先检查是否在 WHERE 子句的字段上建立了索引；如果没有索引，数据库需要全表扫描，在百万级数据下会非常慢。其次看执行计划（EXPLAIN），确认是否走了预期的索引。另外，JOIN 的顺序和选择性也会影响性能。 |
| 简 | 数据增长后几个常因：WHERE 字段无索引致全表扫描、执行计划未走预期索引、JOIN 顺序低效。先用 `EXPLAIN` 看计划。 |
| 精 | 三大常因：WHERE 无索引 → 全表扫描、执行计划走错索引、JOIN 顺序差。先 `EXPLAIN`。 |
| 文言文 | 查询愈慢，多缘全表之扫。先以 `EXPLAIN` 察其执行之道，加索引于 `WHERE` 之列，则速矣。 |

## 安装

### 方式一：marketplace（推荐）

```bash
/plugin marketplace add jaceyang97/moyan
/plugin install moyan@moyan
```

### 方式二：本地 clone

```bash
git clone https://github.com/jaceyang97/moyan ~/.claude/plugins/moyan
```

然后在 Claude Code 中 `/plugin` 启用。

## 快速开始

只需一个命令：

```
/moyan            # 启动（精 = 默认级别，简繁随输入）

# 切级别
/moyan 简         # 正式但紧凑
/moyan 精         # 默认：片段式、短词
/moyan 文言文     # 最省字，古雅

# 切字形
/moyan 简体       # 强制简体
/moyan 繁體       # 强制繁體

# 可组合，顺序不限
/moyan 繁體 文言文

停止莫言           # 恢复正常
```

启动后写 commit、做 code review、答技术问题 —— 一律按莫言风格输出。无需切换。

## 安全边界

以下情况 **自动暂停莫言模式**，完整叙述后再恢复：

- 安全警告
- 不可逆操作确认（删除表、强推、覆盖文件）
- 多步顺序指令（片段排序易误）
- 用户明确要求澄清

## 涵盖场景

主技能 `moyan` 启动后自动覆盖：

| 场景 | 行为 |
|------|------|
| 普通问答 | 按当前级别（简 / 精 / 文言文）压缩输出 |
| 写 commit | 转 Conventional Commits，标题 ≤50 字符，only-when-needed body |
| code review | 一行式：`L42: 重：user 可空。加判空守卫。` |
| 安全 / 破坏性操作 | 自动暂停压缩，完整叙述后恢复 |

## 仓库结构

```
moyan/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   └── moyan/SKILL.md
├── benchmark/
│   ├── RESULTS.md           # 当前版本的 benchmark 数字
│   ├── AUTOSKILL.md         # 自动优化 proposer 的 system prompt
│   ├── prompts.jsonl        # 52 条测试集
│   ├── splits/              # train/holdout 分割
│   └── *.py                 # run / judge / analyze / autoskill
├── README.md
└── LICENSE
```

核心插件部分（`.claude-plugin/` + `skills/`）无脚本、无依赖、无 hooks——一个 SKILL.md 装下全部行为。`benchmark/` 是开发过程工具，不影响插件使用。

## 致谢 / 缘起

- [Julius Brussee / caveman](https://github.com/JuliusBrussee/caveman) —— 原作。本仓库的初衷：向原作者提的 PR [#76](https://github.com/JuliusBrussee/caveman/pull/76) 迟迟未合并，遂单开一仓以飨中文用户。
- 莫言先生 —— 借名

## License

MIT
