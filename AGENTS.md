# AGENTS.md — ASR（AI Software Runtime）

## 状态

**Phase 1-4 已实现。** 72 个测试，6 个 Agent，收敛循环可用。Demo 已在 GLM-4.7-FP8 上测试（2/3 Bug 修复）。

## 快速开始

```bash
source venv/bin/activate
pip install -e .
pip install pytest-json-report pytest-cov   # 必须安装，非可选
pytest tests/                                 # 72 个测试必须全过
```

## 关键陷阱（踩过才知）

### LLM 配置
- `.env` 由 `asr/config/loader.py` 中的 `_load_dotenv()` 读取，**不是** python-dotenv
- 模型名**必须**带 `openai/` 前缀：`openai/glm-4.7-fp8`（缺少 `/` 时代码自动补前缀）
- GLM-4.7-FP8 是推理模型：`max_tokens` 太小会导致 `content` 为 null → 需调到 8192+

### Patch 系统
- PatchEngine 使用**模糊匹配**（`_fuzzy_match`）——不要改回精确匹配
- `parse_diff()` 自动去除 git diff 头部的 `a/` 和 `b/` 前缀
- `apply()` 模糊匹配失败时回退到 GNU `patch -s`——`-s` 标志**至关重要**（阻止 "patching file..." 输出混入文件）

### TesterAgent
- 编译检查在 pytest **之前**执行——编译失败时 Controller 视为 `test_failed`（不跳过）
- `_measure_coverage()` 读取 `pytest --cov` 生成的 `.coverage` 文件——需要 pytest-cov

### 收敛循环
- `test_error`（编译/lint 失败）→ `test_failed = True` → 进入 REPAIRING
- Patch 失败**不会**立即 STUCK——循环会重试下一轮
- `_repairing_phase` 同时从 `TEST_FAILED` 和 `TEST_ERROR` 事件中提取失败信息
- Mesh agent 按代码变更缓存（`_mesh_cache`），`patch_applied` 时清空

### DAG
- `spec.features > 1` 时自动触发，但如果所有 feature 指向同一文件则跳过
- `_resolve_file_conflicts()` 为同文件节点自动添加顺序依赖
- STUCK 节点现在会释放依赖节点（不会死锁）

### Python 注意
- `dict.setdefault()` 是正确的——不要改成 `setdefault`
- Controller 中的 `asyncio.sleep(0.1)` 是有意为之（事件轮询窗口）

## 架构（6 个 Agent）

| Agent | 状态 | 触发事件 |
|-------|------|---------|
| BuilderAgent | 有状态（`_history`） | TASK_CREATED, PATCH_GENERATED, TEST_FAILED |
| TesterAgent | 无状态 | TEST_STARTED |
| AnalyzerAgent | 无状态 | SPEC_DIFF_FOUND |
| SecurityAgent | 无状态 | SPEC_DIFF_FOUND（mesh） |
| PerformanceAgent | 无状态 | SPEC_DIFF_FOUND（mesh） |
| ArchitectureAgent | 无状态 | SPEC_DIFF_FOUND（mesh） |

## 常用命令

```bash
# 运行 Demo
asr run --project demo_project/ --spec demo_project/spec.yaml --max-iterations 10

# 单个测试
pytest tests/test_convergence.py -v

# 全部测试
pytest tests/ -v

# 重新运行前清理事件历史
rm -f .runtime/events/*.json
```

## 禁止修改的文件

- `demo_project/main.py` — 含有 3 个故意注入的 Bug（测试基线）
- `demo_project/test_main.py` — 预写测试，ASR 不得修改
- `.env` — LLM 凭证

## 设计文档

`AI Software Runtime（ASR）系统设计文档.md` — 架构变更前阅读 §7-15。
