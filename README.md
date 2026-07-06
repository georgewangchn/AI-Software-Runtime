# ASR — AI Software Runtime

[![GitHub Pages](https://img.shields.io/badge/在线演示-GitHub%20Pages-blue)](https://georgewangchn.github.io/AI-Software-Runtime/)
[![Version](https://img.shields.io/badge/version-2.0-green)](#)

ASR（AI Software Runtime）是一个基于**控制论**的自治式 AI 软件工程收敛运行时。通过 Builder → Tester → Analyzer 的闭环迭代，从设计文档（`DESIGN.md`）出发，自动生成完整的工程项目代码，并持续收敛直到测试全部通过且规格对齐。

> **在线演示**: [georgewangchn.github.io/AI-Software-Runtime](https://georgewangchn.github.io/AI-Software-Runtime/) — 系统效果验证测试报告，对比四种方案的实际生成效果。

## 为什么开源

2026 年 6 月 10 日，我在朋友圈看到一篇关于 **Loop Engineering（循环工程）** 的报道[[1]](#参考)，深有感触——

> *"你不再是给 Agent 写提示词的人。**你的工作是写循环。**"* — Boris Cherny, Anthropic Claude Code 负责人
>
> *"你不该再给编程 Agent 写提示词了。**你应该设计循环，让循环去提示你的 Agent。**"* — Peter Steinberger, OpenClaw 作者

这正是 ASR 在过去三个月里做的事情：不是在和 LLM 斗智斗勇写提示词，而是在设计一个**收敛运行时**——Builder 生成 → Tester 验证 → Analyzer 裁决 → 循环修复，直到代码真正对齐规格。

**这件事的起点要追溯到今年 3、4 月份。** 当时我在做 Agent 开发，整个行业都在转向 AI 工具辅助编程。但我面临一个现实问题：没有 Claude，没有 GPT 的 token 配额。我只有公司内部免费提供的 **GLM-4.7-FP8**。后来腾讯开放了 WorkBuddy 的免费 token，但也很快耗尽。

于是我开始琢磨：能不能把一个"弱模型"用工程手段堆叠成一个"强系统"？

这就是 ASR 的核心命题——**用不限量的 GLM-4.7-FP8，通过多 Agent 协作 + 验证驱动 + 收敛循环，实现接近甚至超越 GLM-5.1 的效果。**

看到 Loop Engineering 成为行业共识的那一刻，我意识到这件事不应该只放在比赛提交材料里。独立开发者、没有昂贵模型配额的人，应该能用同样的方法做同样的东西。所以今天开源。

---

### 参考

1. [Loop Engineering：当提示词工程成为过去式](https://mp.weixin.qq.com/s/qCbyqmrMQ_P-uM1RzfO6gw) — 微信公众号，2026-06-10

---

## 核心思想

> **一个弱模型 + 强约束系统 > 一个强模型 + 无约束系统**

ASR 的本质是一个**控制论系统**——把 LLM 当执行器（不可控、有随机性），用闭环反馈机制驱动它稳定收敛到目标状态：

```
目标（DESIGN.md）→ 控制器（ASRController）→ 执行器（Builder/LLM）→ 被控对象（代码）
                                                                            ↓
                                        反馈 ← 传感器（Tester pytest + Analyzer 语义）
```

**v2.0 控制论优化体系**（经六轮第一性原理推演验证）：

| 控制论要求 | ASR 实现 |
|-----------|---------|
| **反馈信号可靠** | test_pass_rate 地面真值（pytest 客观结果），Analyzer 噪声信号降级为 logging-only |
| **执行器可约束** | RepairMode 状态机（6 种模式）+ Patch 限幅 + Formal Guards（测试删除/语法检查/Bypass 检测） |
| **系统稳定** | 振荡检测（三重指纹）+ Circuit Breaker + 退化回滚（_best_snapshot）+ Hysteresis 防抖 |
| **可观测** | ConvergenceMetrics（15+ 字段）+ 全事件文件化存储 + 可回放 |
| **可控制** | RepairMode 自动切换 + FINAL_VERIFICATION 防假收敛 + Failure Fingerprint |

---

## 工作原理

```
DESIGN.md（规格文档）
     │
     ▼
┌──────────────────────────────────────────────────┐
│                ASR 收敛运行时                      │
│                                                  │
│  ① REPAIRING  →  ② TESTING  →  ③ ANALYZING      │
│     Builder        Tester        Analyzer         │
│     生成/修复       pytest验证     语义对比DESIGN    │
│       ▲               │              │            │
│       │          退化检测         对齐?            │
│       │          _best_snapshot    ↓               │
│       └── 修复指令 ←──┴──── CONVERGED              │
│                                                  │
│  ④ 控制论决策（每轮）                               │
│     ConvergenceMetrics → trend/oscillation       │
│     Circuit Breaker → 连续N轮无改善则停            │
│     RepairMode auto-switch → hysteresis 切换      │
└──────────────────────────────────────────────────┘
     │
     ▼
完整工程项目（含测试、文档）
```

---

## 环境要求

- **操作系统**：macOS / Linux
- **Python**：3.12.9（通过 pyenv 管理）
- **opencode CLI**：>= 1.15（需配置好 LLM 模型提供商）
- **oh-my-openagent**（可选，推荐）：opencode 多智能体编排插件，启用后显著提升代码质量

## 快速开始

### 1. 安装 pyenv 和 Python

```bash
# macOS
brew install pyenv

# 配置 shell（~/.zshrc 或 ~/.bashrc）
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc
source ~/.zshrc

# 安装 Python 3.12.9
pyenv install 3.12.9
```

### 2. 克隆项目并配置环境

```bash
git clone https://github.com/your-username/asr.git
cd asr

# 设置 Python 版本
pyenv local 3.12.9

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置 LLM

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入你的 LLM 接口地址和 API Key
# 支持任意 OpenAI 兼容接口（vLLM / Ollama / OpenAI 官方等）
```

`.env` 配置示例（详见 `.env.example`）：

```ini
FEASIBILITY_LLM_API_BASE=http://localhost:8000/v1
FEASIBILITY_LLM_API_KEY=your-api-key
FEASIBILITY_LLM_MODEL=your-model-name
FEASIBILITY_LLM_CONTEXT=131072
```

### 4. 准备设计文档（DESIGN.md）

`DESIGN.md` 是 ASR 的**规格输入**，描述你想要生成的软件系统的设计需求，包括：

- 功能需求（模块、接口、数据结构）
- 架构约束（分层设计、依赖关系）
- 测试要求（单测覆盖率、集成测试）

> **关于 DESIGN.md**：每个项目需要自己编写 DESIGN.md，描述待生成软件的规格。这是 ASR 的核心输入，决定了最终生成代码的功能和结构。你可以参考 [AI Software Runtime(ASR)技术报告](./AI%20Software%20Runtime(ASR)技术报告.md) 中的案例了解规格文档的写法。

### 5. 运行 ASR

```bash
# 创建项目目录，放入 DESIGN.md
mkdir -p my_project
cp /path/to/your/DESIGN.md my_project/DESIGN.md

# 运行 ASR（最多迭代 20 轮）
python -m asr.cli.main run --project my_project --max-iterations 20
```

或复制并修改启动脚本：

```bash
cp start.sh my_start.sh
# 编辑 my_start.sh 中的路径和参数
bash my_start.sh
```

**运行时输出示例**：

```
ASR 收敛运行时 [直接模式]
项目路径: my_project
最大迭代轮次: 20

  [第1轮] 代码生成  错误:0  🔧  | 补丁:0 文件:3 代码行:156 初始生成
  [第2轮] 测试验证  错误:3  ❌  | 通过:12/15 失败:test_foo,test_bar
  [第3轮] 代码修复  错误:3  🔧  | 修复3个失败 pass_rate=0.80 trend=improving
  [第4轮] 测试验证  错误:0  ✅  | 通过:15/15
  [第5轮] 规格分析  错误:0  ✅  | 规格:一致

✅ 已收敛 — 所有测试通过且规格一致
迭代轮次: 5 | 事件数: 23
```

## 验证安装

```bash
python -m asr.cli.main --help
```

---

## 项目结构

```
asr/
├── asr/                            # ASR 核心代码
│   ├── agents/                     # 智能体实现
│   │   ├── builder.py              # Builder Agent：代码生成与修复（带会话延续）
│   │   ├── tester.py               # Tester Agent：测试生成 + pytest 执行（Sandbox 隔离）
│   │   ├── analyzer.py             # Analyzer Agent：diff-only 模式 + 结构化偏差分析
│   │   ├── opencode_backend.py     # opencode CLI 子进程调用后端
│   │   └── llm_tracker.py          # Token 消耗追踪
│   ├── controller/
│   │   └── convergence.py          # 收敛控制器：控制论指标 + RepairMode 状态机 + 退化回滚（~1350行）
│   ├── cli/
│   │   └── main.py                 # CLI 入口
│   ├── config/
│   │   ├── models.py               # Pydantic v2 配置模型（含控制论参数）
│   │   └── loader.py               # 配置加载（支持 .env）
│   ├── events/                     # 20 种事件类型 + EventStore（文件化 A2A 通信）
│   ├── dag/                        # Task DAG 并行执行
│   └── runtime.py                  # 运行时入口
├── tests/                          # 单元测试
├── demo_dev/                       # Demo 工程
├── .env.example                    # 环境变量配置模板
├── start.sh                        # 启动脚本示例
├── requirements.txt                # Python 依赖
├── index.html                      # 系统效果验证测试报告（GitHub Pages 首页）
└── README.md
```

---

## 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEASIBILITY_LLM_API_BASE` | ✅ | OpenAI 兼容接口地址 |
| `FEASIBILITY_LLM_API_KEY` | ✅ | API 密钥（本地部署可填 `empty`） |
| `FEASIBILITY_LLM_MODEL` | ✅ | 模型名称 |
| `FEASIBILITY_LLM_CONTEXT` | 可选 | 上下文窗口大小（默认 131072） |
| `ASR_OPENCODE_TIMEOUT` | 可选 | opencode 调用超时秒数（默认 24400） |
| `ASR_VERBOSE` | 可选 | 设为 `1` 启用详细日志 |

---

## 依赖说明

| 包 | 用途 |
|----|------|
| `pydantic` | 数据模型校验 |
| `pyyaml` | YAML 配置解析 |
| `litellm` | 统一 LLM 调用接口（支持 OpenAI / Anthropic 等） |
| `openai` | OpenAI 兼容 API 客户端 |
| `whatthepatch` | Diff/Patch 解析与应用 |
| `filelock` | 文件锁（事件原子写入） |
| `click` | CLI 框架 |
| `rich` | 终端美化输出 |
| `pytest` | 测试框架 |
| `pytest-asyncio` | 异步测试支持 |
| `pytest-json-report` | pytest JSON 报告 |
| `pytest-cov` | 测试覆盖率 |
| `fastapi` + `uvicorn` | Web API（可选） |
| `httpx` | HTTP 客户端 |

---

## v2.0 控制论优化亮点

### RepairMode 状态机

六种修复模式，每种实质改变 Controller 对 Builder 的调用方式，通过 hysteresis 自动切换：

```
INITIAL_GENERATION → TEST_FIX ←────────────────────┐
                       ↓ (stalled ≥ 2)              │
                   SPEC_COMPLETION                   │
                       ↓ (oscillation ≥ 0.7)        │
                   OSCILLATION_BREAK ──(improving ≥ 2)──┘
                       ↓ (regressing ≥ 2)
                   REGRESSION_RECOVERY ──(improving ≥ 1)──→ TEST_FIX
                       ↓ (tests pass, no analyzer)
                   FINAL_VERIFICATION ──(Analyzer: ALL CLEAR)──→ 收敛
```

### Formal Guards（硬约束三件套）

| Guard | 检测内容 | 动作 |
|-------|---------|------|
| 测试删除检测 | Builder 删除了 test_*.py 或 tests/ 下的文件 | 拒绝 patch + 回滚 |
| 语法检查 | 对所有 .py 文件（含新建）执行 `ast.parse()` | 拒绝 patch + 回滚 |
| Bypass 检测 | `except:`、`return expected`、`@pytest.mark.skip`、生产代码中的 `mock` | 拒绝 patch + 回滚 |

### 退化回滚（_best_snapshot）

test_pass_rate 创新高时保存项目文件快照，持续退化时恢复到最佳状态——不依赖 LLM 判断，纯文件级回滚。

---

## 相关文档

### 项目演进

ASR 的设计思路经历了从原始构想到工程落地的完整演进：

| 阶段 | 文档 | 说明 |
|------|------|------|
| 原始构想 | [Supervise-Agent：有监督长任务自动化软件工程系统.md](./Supervise-Agent：有监督长任务自动化软件工程系统.md) | 项目最初的想法：分层裁决 + 多Agent协同 + 工程约束，利用低成本开源模型实现接近高端模型的稳定性 |
| 工程落地 + 控制论优化 | [AI Software Runtime(ASR)技术报告.md](./AI%20Software%20Runtime(ASR)技术报告.md) | 完整技术报告（v2.0），含系统架构设计、控制论优化体系、端到端验证、DAG 调度、事件总线、配置模型等 |

> **阅读建议**：建议先读原始构想理解"为什么需要这个系统"，再读技术报告了解"怎么实现的 + 控制论怎么优化的"。

### 其他

- [系统效果验证测试报告](./系统效果验证测试报告.html) — 对比测试结果与分析

---

## License

MIT
