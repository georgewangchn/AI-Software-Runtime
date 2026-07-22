# ASR "拿来即用"评估报告

## 一、第一性原理推演：用户拿来即用的路径

一个新用户 clone 仓库后，"拿来即用"的路径是：

```
1. git clone → 2. 安装依赖 → 3. 配置 LLM → 4. 创建项目 → 5. asr run → 6. 自动收敛
```

逐层检查每一步是否有阻塞：

## 二、逐层检查结果

### ❌ 阻塞 1：无法 pip install（没有 pyproject.toml / setup.py）

**现状**：项目没有 `pyproject.toml` 或 `setup.py`，无法 `pip install -e .`。用户必须手动 `sys.path.insert` 或设置 `PYTHONPATH`。

**反事实推演**：假设用户 `git clone` 后直接 `python -m asr.cli.main run --project ./myproject`：
- Python 找不到 `asr` 包 → `ModuleNotFoundError`
- 必须先 `pip install -r requirements.txt` + 手动设置 PYTHONPATH
- 这不是"拿来即用"

### ❌ 阻塞 2：opencode CLI 依赖无配置引导

**现状**：ASR 的 Builder/Tester/Analyzer 全部通过 `opencode run` CLI 调用 LLM。但：
- 用户需要自己安装 opencode（`npm install -g opencode-ai`）
- 用户需要自己配置 opencode 的 provider/model（`~/.config/opencode/opencode.json`）
- ASR 代码中没有检查 opencode 是否可用
- ASR 代码中没有引导用户配置 opencode

**反事实推演**：假设用户安装了 opencode 但没配置 provider：
- `opencode run` 会报错 "no model configured"
- ASR 的 Builder 收到 empty output → FakeDeathError → 无限重试
- 用户完全不知道是 opencode 配置问题

### ❌ 阻塞 3：.env 文件格式损坏

**现状**：`.env` 文件中有 `FEASIBILITY_LLM_API_BASE==http://...`（两个等号），且变量名不匹配 `create_default_config()` 的读取逻辑。

`create_default_config()` 读取：
- `FEASIBILITY_LLM_MODEL` → `.env` 中有但值是 `qwen3-next-80b-a3b-instruct`
- `FEASIBILITY_LLM_API_BASE` → `.env` 中有但值前面多了一个 `=`
- `FEASIBILITY_LLM_API_KEY` → `.env` 中有

`_load_dotenv()` 用 `partition("=")` 分割，`FEASIBILITY_LLM_API_BASE==http://...` 会被解析为 key=`FEASIBILITY_LLM_API_BASE`, val=`=http://...`（多了一个前导 `=`）。

**反事实推演**：API base 变成 `=http://192.168.1.57:9988/v1` → HTTP 请求失败 → opencode 可能也不使用这个值（它有自己的配置）→ 但如果 ASR 未来直接调用 API（不通过 opencode），这里会出问题。

### ❌ 阻塞 4：opencode 与 ASR 的 LLM 配置是两套独立系统

**现状**：
- ASR 的 `create_default_config()` 从 `.env` 读取 LLM 配置 → 但这些配置**只存在 ASRConfig 对象中，从不被使用**
- opencode 有自己的配置文件 `~/.config/opencode/opencode.json` → 这才是实际生效的 LLM 配置
- ASR 的 `ModelConfig` 中的 `api_base`、`api_key`、`model` 字段是死代码——`opencode_backend.py` 只调用 `opencode run`，不传递任何 LLM 配置

**反事实推演**：用户按 ASR 文档配置了 `.env`，但 opencode 使用的是自己配置的 model → 两者不一致 → 用户困惑"为什么我配了 GLM 但 opencode 在用 deepseek"

### ❌ 阻塞 5：没有 `asr init` 生成示例 DESIGN.md

**现状**：`asr init` 只创建目录结构和 `asr_config.yaml`，不生成示例 `DESIGN.md`。新用户不知道 DESIGN.md 应该写什么格式。

### ⚠️ 阻塞 6：requirements.txt 包含不必要的依赖

**现状**：`requirements.txt` 包含 `fastapi`、`uvicorn`、`httpx`、`litellm`、`rich`、`whatthepatch` 等，但代码中：
- `fastapi`/`uvicorn` — 从未 import
- `litellm` — 从未 import（用的是 opencode CLI）
- `rich` — 从未 import
- `whatthepatch` — 从未 import
- `httpx` — 从未 import

实际需要的依赖只有：`pydantic`、`pyyaml`、`filelock`、`click`、`pytest`、`pytest-asyncio`

### ❌ 阻塞 7：没有 entry_points（`asr` 命令不可用）

**现状**：用户必须用 `python -m asr.cli.main run ...`，不能用 `asr run ...`。因为没有 `pyproject.toml` 定义 `[project.scripts]`。

## 三、优化方案

### 修复 1：创建 pyproject.toml（P0）

**方案**：创建标准 `pyproject.toml`，定义包信息、依赖、entry_points。

**可行性**：✅ 标准操作，无风险。

### 修复 2：清理 requirements.txt（P0）

**方案**：移除未使用的依赖，只保留实际需要的。

**可行性**：✅ 直接删除即可。

### 修复 3：创建 `asr init` 模板生成（P0）

**方案**：`asr init` 生成示例 DESIGN.md + opencode 配置指引。

**可行性**：✅ 修改 cli/main.py 的 init 命令。

### 修复 4：启动时检查 opencode 可用性（P0）

**方案**：在 `asr run` 执行前检查 `opencode` 是否在 PATH 中、是否有配置文件。

**可行性**：✅ 简单的 subprocess 检查。

### 修复 5：修复 .env 格式（P0）

**方案**：修复 `==` 为 `=`，清理变量名。

**可行性**：✅ 直接修复。

### 修复 6：添加 opencode 配置模板（P1）

**方案**：`asr init` 生成 `.opencode/config.json` 模板，引导用户配置 LLM provider。

**可行性**：✅ 生成模板文件。

### 修复 7：清理 ASRConfig 中的死代码（P1）

**方案**：`create_default_config()` 中的 `api_base`/`api_key`/`model` 字段标注为 "仅用于参考，实际 LLM 配置通过 opencode 管理"。

**可行性**：✅ 添加注释和文档。
