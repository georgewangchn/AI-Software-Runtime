# ASR — AI Software Runtime

ASR（AI Software Runtime）是一个基于**多智能体协作**的自动化软件工程系统。通过 Builder → Tester → Analyzer 的闭环迭代，从设计文档（`DESIGN.md`）出发，自动生成完整的工程项目代码，并持续收敛直到测试全部通过。

> **效果演示**: 查看 [系统效果验证测试报告](./系统效果验证测试报告.html)，对比 opencode CLI / ASR 初版 / ASR+ / longdoc 四种方案的实际生成效果。

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

## 工作原理

```
DESIGN.md（规格文档）
     │
     ▼
┌─────────────────────────────────────────┐
│              ASR 收敛运行时              │
│                                         │
│  Builder ──► Tester ──► Analyzer        │
│     ▲                      │            │
│     └──── 修复指令 ◄────────┘            │
│                                         │
│  迭代直到：所有测试通过 + 规格对齐        │
└─────────────────────────────────────────┘
     │
     ▼
完整工程项目（含测试、文档、Pack 元数据）
```

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

> **关于 DESIGN.md**：每个项目需要自己编写 DESIGN.md，描述待生成软件的规格。这是 ASR 的核心输入，决定了最终生成代码的功能和结构。你可以参考 [AI Software Runtime(ASR)技术报告](./AI%20Software%20runtime(ASR)技术报告.md) 中的案例了解规格文档的写法。

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

## 验证安装

```bash
python -m asr.cli.main --help
```

## 项目结构

```
asr/
├── asr/                        # ASR 核心代码
│   ├── agents/                 # 智能体实现
│   │   ├── builder.py          # Builder Agent：代码生成与修复
│   │   ├── tester.py           # Tester Agent：pytest 执行与验证
│   │   ├── analyzer.py         # Analyzer Agent：规格对齐分析
│   │   └── opencode_backend.py # opencode CLI 调用后端
│   ├── controller/
│   │   └── convergence.py      # 收敛控制器：迭代循环与终止条件
│   ├── cli/
│   │   └── main.py             # CLI 入口
│   ├── config/                 # 配置加载（支持 .env）
│   ├── events/                 # 事件总线
│   ├── patch/                  # Diff/Patch 应用逻辑
│   └── runtime.py              # 运行时入口
├── .env.example                # 环境变量配置模板（复制为 .env 后填写）
├── start.sh                    # 启动脚本示例
├── requirements.txt            # Python 依赖
├── index.html                  # 系统效果验证测试报告（GitHub Pages 首页）
└── README.md
```

## 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEASIBILITY_LLM_API_BASE` | ✅ | OpenAI 兼容接口地址 |
| `FEASIBILITY_LLM_API_KEY` | ✅ | API 密钥（本地部署可填 `empty`） |
| `FEASIBILITY_LLM_MODEL` | ✅ | 模型名称 |
| `FEASIBILITY_LLM_CONTEXT` | 可选 | 上下文窗口大小（默认 131072） |
| `ASR_OPENCODE_TIMEOUT` | 可选 | opencode 调用超时秒数（默认 24400） |
| `ASR_VERBOSE` | 可选 | 设为 `1` 启用详细日志 |

## 依赖说明

| 包 | 用途 |
|----|------|
| `pydantic` | 数据模型校验 |
| `pyyaml` | YAML 配置解析 |
| `litellm` | 统一 LLM 调用接口（支持 OpenAI / Anthropic 等） |
| `click` | CLI 框架 |
| `rich` | 终端美化输出 |
| `pytest` | 测试框架 |
| `fastapi` + `uvicorn` | Web API（可选） |
| `httpx` | HTTP 客户端 |

## 相关文档

### 项目演进

ASR 的设计思路经历了两次迭代，展现了从原始构想到工程落地的完整思路：

| 阶段 | 文档 | 说明 |
|------|------|------|
| 原始构想 | [Supervise-Agent：有监督长任务自动化软件工程系统.md](./Supervise-Agent：有监督长任务自动化软件工程系统.md) | 项目最初的想法：分层裁决 + 多Agent协同 + 工程约束，利用低成本开源模型实现接近高端模型的稳定性 |
| 方案细化 | [AI Software Runtime(ASR)系统设计文档.md](./AI%20Software%20Runtime(ASR)系统设计文档.md) | 在原始构想基础上的完整工程设计方案，包含 DAG 调度、事件总线、收敛控制、Patch 管理等核心模块 |

> **阅读建议**：建议先读原始构想理解"为什么需要这个系统"，再读系统设计文档了解"怎么实现的"。

### 其他

- [AI Software Runtime(ASR) 技术报告](./AI%20Software%20runtime(ASR)技术报告.md) — 系统架构与设计原理
- [系统效果验证测试报告](./系统效果验证测试报告.html) — 对比测试结果与分析
