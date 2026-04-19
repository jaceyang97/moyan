# 莫言 · moyan

中文省 token 模式，Claude Code 插件。三档级别：简 / 精 / 文言文，简繁体跟你输入走。

## 效果

举个例子。问「我的 Docker 容器启动后立即退出，为什么？」：

| 模式 | 回复 |
|------|------|
| 原始 | 好的，容器启动后立即退出通常有几个原因。最常见的是容器的主进程（ENTRYPOINT/CMD 指定的命令）执行完成或者崩溃了 —— 实际上 Docker 会跟随主进程的生命周期，主进程结束容器就停了。可以用 `docker logs <container-id>` 看退出前的输出，排查是不是报错退出。也有可能是 CMD 写法的问题，比如用 shell form 而不是 exec form 导致信号处理异常。如果是基于 scratch 或 distroless 镜像，还要确认二进制文件的架构是否匹配（x86_64 vs arm64）。 |
| 简 | 容器主进程结束则容器停。三大常因：1) 主进程 crash — `docker logs <id>` 看输出；2) CMD 用了 shell form，改 exec form；3) 二进制架构不匹配（x86 vs arm）。 |
| 精 | 主进程退 → 容器停。查：`docker logs <id>` / CMD 改 exec form / 架构对齐（x86 vs arm）。 |
| 文言文 | 容器之生，系于主进程之存，主进程退则容器亡。先以 `docker logs <id>` 察其末言，次验 CMD 是否 exec form，终验架构符否（x86 vs arm）。 |

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

71 条编程 prompt（4 难度 × 8 类别，53 训 18 holdout），用 Sonnet 4.6 跑五组对照（英文 normal、中文 normal、莫言三档），Opus 4.7 做判官。SKILL.md 起初是手写 + autoskill 自迭代出来的；最新一轮把 SKILL 缩了 29% 同时加一条版式规则（去 `---` 横线与短答 `##` 标题），holdout 上又涨了 5pp。

holdout 18 条，output token 相对中文 normal 省的中位数：

| 级别 | 中位 | 均值 | 适合 |
|---|---|---|---|
| 简 | 73% | 67% | 正式文档、对外沟通 |
| 精（默认）| 74% | 66% | 日常开发问答 |
| 文言文 | **75%** | **68%** | debug、概念解释这类 |

文言文在最难压的类目（debug / explain / howto）比精多省 8-12pp。语法天然就紧：没有的/了/着，介词少，倒装允许。但 commit 是例外 —— commit message 需要 feat / fix 这些英文关键字，文言文反而拖长。所以 SKILL.md 里规定 commit 不套级别压缩，走 Conventional Commits。

![progression](docs/progression.png)

完整数字、per-category 表、autoskill 迭代日志、复现命令：[`benchmark/RESULTS_v2.md`](benchmark/RESULTS_v2.md) · [`benchmark/program.md`](benchmark/program.md)。

## 仓库结构

```
moyan/
├── .claude-plugin/             # 插件元数据
├── skills/moyan/SKILL.md       # 本体：所有行为规则都在这一个文件
├── benchmark/                  # autoresearch 风格的自迭代 loop
│   ├── program.md              # loop 规范（agent 自己跑，没有 Python 编排器）
│   ├── evaluate.py             # 单标量指标
│   ├── run.py / judge.py / lib.py
│   ├── plot.py                 # 画 progression chart
│   ├── prompts.jsonl / splits/
│   └── results.tsv / RESULTS{,_v2}.md / RUNS.md
├── docs/progression.png
└── README.md / LICENSE
```

装插件只用到 `.claude-plugin/` + `skills/`，`benchmark/` 是开发工具，运行时用不到。

## 致谢

- [Julius Brussee / caveman](https://github.com/JuliusBrussee/caveman) —— 原作。这仓库的缘起是给 caveman 提了 PR [#76](https://github.com/JuliusBrussee/caveman/pull/76) 加中文支持，合得慢，索性单开一仓。

## License

MIT
