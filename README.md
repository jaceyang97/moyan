# 莫言 · moyan

中文省 token 模式，Claude Code 插件。

想法来自 [caveman](https://github.com/JuliusBrussee/caveman)：caveman 让 Claude 用山顶洞人式英文回答省 token，moyan 换成简洁中文做同件事。三档级别：简 / 精 / 文言文，简繁体跟你输入走。

## 效果

举个例子。问「为什么我这条 SQL 查询越来越慢？」：

| 模式 | 回复 |
|------|------|
| 原始 | 随着数据量增长，查询变慢通常有几个原因。首先检查是否在 WHERE 子句的字段上建立了索引；如果没有索引，数据库需要全表扫描，在百万级数据下会非常慢。其次看执行计划（EXPLAIN），确认是否走了预期的索引。另外，JOIN 的顺序和选择性也会影响性能。 |
| 简 | 数据增长后几个常因：WHERE 字段无索引致全表扫描、执行计划未走预期索引、JOIN 顺序低效。先用 `EXPLAIN` 看计划。 |
| 精 | 三大常因：WHERE 无索引 → 全表扫描、执行计划走错索引、JOIN 顺序差。先 `EXPLAIN`。 |
| 文言文 | 查询愈慢，多缘全表之扫。先以 `EXPLAIN` 察其执行之道，加索引于 `WHERE` 之列，则速矣。 |

在 52 条编程问答上用 Sonnet 4.6 测了一轮，对比中文 normal 回答，output token 能省这么多：

| 级别 | 中位 | 均值 | 适合 |
|---|---|---|---|
| 简 | 64% | 63% | 正式文档、对外沟通 |
| 精（默认）| 66% | 67% | 日常开发问答 |
| 文言文 | **71%** | **70%** | debug、概念解释这类 |

有意思的是，文言文在最难压的类目（debug / explain / howto）反而比精多省 8-12pp。语法天然就紧：没有的/了/着，介词少，倒装允许。

但 commit 是例外。commit message 需要 feat / fix 这些英文关键字，文言文反而拖长，精比它好 9pp。所以 SKILL.md 里规定 commit 不套级别压缩，老实走 Conventional Commits。

## 安装

```bash
# marketplace（推荐）
/plugin marketplace add jaceyang97/moyan
/plugin install moyan@moyan

# 或本地 clone
git clone https://github.com/jaceyang97/moyan ~/.claude/plugins/moyan
```

装完用 `/moyan` 启动：

```
/moyan            # 默认「精」
/moyan 简
/moyan 文言文
/moyan 简体       # 切字形
/moyan 繁體
/moyan 繁體 文言文 # 可组合
停止莫言           # 关闭
```

启动后写 commit、做 code review、答技术问题，一律按当前级别输出。只有几种情况会自动暂停、完整说话：安全警告、不可逆操作（删表、强推、覆盖文件）、多步顺序操作、用户明确说「说详细点」。讲完之后自动恢复。

## Benchmark

52 条编程 prompt，分 4 难度 × 8 类别，39 训 13 holdout。5 组对照：英文 normal、中文 normal、莫言三档。响应用 Sonnet 4.6，判官 Opus 4.6 —— 故意跨家族，避免自评。

![progression](docs/progression.png)

v1 第一版手写规则起步 52.7%，加规则到 61%。之后 Sonnet 4.5 升到 4.6 自带 +5pp，切文言文级别再 +5pp，到现在 70.6%。最后用 autoskill 跑了 4 轮自动迭代，全部 discard —— 说明 SKILL.md 在这个模型上已经撞到天花板，再改规则就是在噪声里打转。接下来的收益大概率来自模型升级或级别切换，不是新规则。

完整数字、per-category 表、复现命令：[`benchmark/RESULTS_v2.md`](benchmark/RESULTS_v2.md)。v1 历史：[`RESULTS.md`](benchmark/RESULTS.md)。autoskill loop 设计：[`benchmark/program.md`](benchmark/program.md)。

## 仓库结构

```
moyan/
├── .claude-plugin/             # 插件元数据
├── skills/moyan/SKILL.md       # 本体：所有行为规则都在这一个文件
├── benchmark/                  # autoresearch 风格的自迭代 loop
│   ├── program.md              # loop 规范（agent 自己跑，没有 Python 编排器）
│   ├── evaluate.py             # 单标量指标
│   ├── lib.py / run.py / judge.py
│   ├── plot.py                 # 画 progression chart
│   ├── prompts.jsonl / splits/
│   └── results.tsv / RESULTS{,_v2}.md
├── docs/progression.png
└── README.md / LICENSE
```

装插件只用到 `.claude-plugin/` + `skills/`，`benchmark/` 是开发工具，运行时用不到。

## 致谢

- [Julius Brussee / caveman](https://github.com/JuliusBrussee/caveman) —— 原作。这仓库的缘起是给 caveman 提了 PR [#76](https://github.com/JuliusBrussee/caveman/pull/76) 加中文支持，合得慢，索性单开一仓。
- 莫言先生 —— 借名。

## License

MIT
