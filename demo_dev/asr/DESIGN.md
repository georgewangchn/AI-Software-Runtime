# 可研报告编译器设计方案 v4.3

> 版本：v4.3 | 日期：2026-05-14
> 定位：可研报告编译器——从用户自然语言到结构化可研报告的声明式知识编译系统

---

## 零、版本历史

| 版本 | 日期 | 核心变更 |
|------|------|---------|
| v1.0 | 2026-04-09 | Pack 层完整工程设计规范初版 |
| v2.0 | 2026-04-10 | Fact 权限冲突模型、长任务恢复、预算正向推算 |
| v3.0 | 2026-04-11 | 存储全文件化、单向补充约束、双层渲染 |
| v3.1 | 2026-04-12 | 用户修改双向传播、规则与校验器体系 |
| v3.2 | 2026-04-14 | Human-in-the-loop 两种工作模式、知识迭代机制 |
| v3.3 | 2026-04-15 | 命名体系确立——Pack + Skills + Fact Graph |
| v4.0 | 2026-04-21 | LangGraph 宿主、Pack 动态覆盖/继承、Fact Context 全量注入、动态传播 |
| **v4.0r2** | **2026-04-23** | **文档重构：融入实际实现经验，确立核心设计哲学，消除版本对比冗余** |
| **v4.1** | **2026-04-29** | **新增 §5.7 Runtime/Pack 分层抽象原则；识别并文档化 9 项当前违背项；制定 4 阶段修复路线** |
| **v4.2** | **2026-05-11** | **修复违规 V1/V2/V8/V9；删除 runtime/skills.py 死代码单体；移除 runtime/knowledge/pricing.json；更新 §9 Agent 工作流（含 7 步 DAG、合规/生命周期 Agent）；更新 §14 渲染体系（TOC 驱动渲染 + NarrativeAgent）** |
| **v4.3** | **2026-05-14** | **Pack 模型重构：abc(base→行业) 三级继承 → abc(domain+commons) 平级组合。base 从父层变为 commons Pack，行业 Pack 零继承独立。Agent 清毒：feature_agent / hardware_agent 零行业字符串。Skill 接口统一为 facts: dict。模板支持 {{ asset() }} 通用资产引用。智能更新意图路由从 Pack config 加载。测试基线 73 → 182。** |

---

## 一、核心设计哲学

可研报告编译器的全部设计决策，源于以下四条哲学原则：

### 哲学一：声明式优于命令式

**执行流程由配置声明，而非代码硬编码。**

```
命令式（硬编码）：                    声明式（配置驱动）：
  PIPELINE_STEPS = [                   pack.yaml agents[].depends_on
    "req", "feat", "arch",             行业 Pack 改流程 → 改 pack.yaml
    "hw", "budget"                     无需改源码
  ]                                     DAG 动态构建（Kahn 拓扑排序）
  行业 Pack 改流程 → 改源码 → 发版
```

这一原则贯穿系统每一层：
- **Agent DAG**：从 pack.yaml 的 `agents[].depends_on` 动态构建，不是 Python 列表
- **传播链**：从 Schema 的 `affects` 配置动态构建，不是硬编码 if-elif
- **Section 映射**：从 domain Pack Schema 动态构建，不是字典常量
- **Skill 挂载**：pack.yaml 声明 `allowed_skills`，运行时动态调度

### 哲学二：事实驱动，而非意图猜测

**让 LLM 看到完整数据，由事实决定修改方案，而不是关键词猜测意图。**

```
关键词意图识别（v1）：                   事实驱动分析（v2）：
  关键词匹配 → 单一意图判定                全量 Fact Context 注入 LLM
  重叠、否定式容易误判                     LLM 在完整数据框架内判断
  模糊场景无法处理                        输出结构化修改指令
                                          规则快速匹配 + LLM 深度分析
```

### 哲学三：增量修改，精准重算

**只改用户提到的字段，保留未变更数据，只重跑受影响的下游 Agent。**

```
全量重建（旧）：                        增量修改（新）：
  clear_section("FeatureList")          修改 FeatureList.某个字段
  重跑 feature_agent                    下游 Agent 精准重算
  重跑 software_arch_agent              未变更的 Section 保持不动
  重跑 hardware_agent                   保留用户已确认的数据
  重跑 budget_agent
```

### 哲学四：中文字段，泛化指令

**Fact Schema 字段使用中文命名，使 LLM 生成 fact 指令更精准。**

```
英文字段：                               中文字段：
  corpus_volume_tb: 1000                  语料总规模TB: 1000
  security_level: "high"                  安全等级: "高"
  
  LLM 需理解 corpus_volume_tb 语义         LLM 直接理解字段含义
  可能生成错误字段名                       生成指令更精准
```

---

## 二、系统本质与心智模型

可研报告编译器是一个**声明式知识编译系统（Declarative Knowledge Compiler）**：

```
用户输入需求 + 行业 Pack
         ↓
    Pack Compiler（Orchestrator）
         ↓
   Agent DAG（声明式执行图，LangGraph StateGraph）
         ↓
   Agent ↔ Skill ↔ Fact Graph
         ↓
      Renderer
         ↓
   可研报告（Word/Markdown）
```

**核心约束**：
- LLM 不产生最终内容，只产生结构化变更指令
- 文档是编译产物：Fact Graph → Renderer → Word
- Runtime 强制规则：PermissionGuard + Validator，不靠 Prompt
- Patch Log 是命脉：append-only JSONL，任何时刻可回放重建

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 宿主平台 | **LangGraph** | DAG 状态图 + Checkpointer + 条件边 |
| 兼容入口 | OpenClaw（MCP） | 适配层保留，两套入口并存 |
| Fact Store | `fact_graph.json` | 原子写入（.tmp → rename） |
| Patch Log | `patch_log.jsonl` | append-only WAL |
| Checkpoint | AsyncSqliteSaver | 进程重启可恢复，降级回退 MemorySaver |
| LLM 调用 | litellm | 多模型统一接入 |
| 模板引擎 | Jinja2 | 行业专家可上手，支持 `{{ asset() }}` |
| 文档导出 | python-docx | Word 生成 |

---

## 三、系统运行关系

### 3.1 入口层

```
用户（售前人员）
    │ 自然语言
    ▼
┌─────────────────────────────────────────────────────────────┐
│  LangGraph StateGraph — DAG 状态图主入口                     │
│  · PipelineDAG：从 pack.yaml agents 配置动态构建             │
│  · AsyncSqliteSaver：checkpoint 中断恢复                    │
│  · 条件边：step_by_step 暂停与恢复                           │
│  · OpenClawAdapter：兼容入口（MCP stdio 协议）               │
└────────────────────────┬────────────────────────────────────┘
                         ▼
Orchestrator（可研报告编译器核心）
    │
    ▼
Runtime Kernel → Agent DAG → Fact Store → Renderer
```

### 3.2 调用关系全图

```
┌──────────────────────────────────────────────────────────────┐
│  用户（售前人员）                                              │
│  对话输入："帮我写一个大模型语料平台可研，1000TB多模态语料，覆盖15个语种"       │
└────────────────────┬─────────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────┐  ┌──────────────────────────────────────┐
│  LangGraph 入口  │  │  OpenClaw 入口（兼容保留）              │
│  StateGraph      │  │  Agent → Tool Call → Adapter          │
│  Checkpointer    │  │  MCP stdio（JSON-RPC 2.0）            │
└────────┬─────────┘  └────────────┬─────────────────────────┘
         │                         │
         └──────────┬──────────────┘
                    ▼
┌──────────────────────────────────────────────────────────────┐
│  Orchestrator（纯 Python，零外部依赖）                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  UnifiedLoader│  │  Fact Store  │  │  Patch Log (WAL)   │ │
│  │  (domain+commons│  │  （JSON）     │  │  （JSONL）         │ │
│  │   双通道加载)   │  │              │  │                    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────┘ │
│         │                 │                      │           │
│  ┌──────▼─────────────────▼──────────────────────▼─────────┐ │
│  │              Runtime Kernel（执行引擎）                   │ │
│  │  · DAG 调度（LangGraph StateGraph，依赖就绪→启动节点）   │ │
│  │  · Agent 调用（LLM + Skill 混合执行）                    │ │
│  │  · FactContext 注入（全量 Fact → LLM 上下文）            │ │
│  │  · UpdateAnalyzer（规则快速匹配 + LLM 深度分析）         │ │
│  │  · BidirectionalPropagator（动态传播链）                 │ │
│  │  · Validator（Schema 校验 + 跨节点一致性）               │ │
│  └──────┬──────────────────────────────────────────────────┘ │
└─────────┼────────────────────────────────────────────────────┘
          │ 调用 LLM（litellm 统一接入）
          ▼
    LLM（GLM / GPT / Claude）
          │ 返回结构化变更指令
          ▼
    Runtime Kernel 校验 → 写入 Fact Store
          │
          ▼
    Renderer（Fact → Jinja2 → Markdown/Word）
```

---

## 四、Agent DAG 机制

### 4.1 声明式执行图

Agent DAG 是可研报告编译器的**执行骨架**。每个 domain Pack 在自己的 `pack.yaml` 中声明 Agent 列表和依赖关系，系统通过 Kahn 拓扑排序动态构建执行图。

```yaml
# base/pack.yaml — 通用 5 步流水线
agents:
  - id: requirement_agent
    depends_on: []
    step: 1
  - id: feature_agent
    depends_on: [requirement_agent]
    step: 2
  - id: software_arch_agent
    depends_on: [feature_agent]
    step: 3
  - id: hardware_agent
    depends_on: [software_arch_agent]
    step: 4
  - id: budget_agent
    depends_on: [hardware_agent]
    step: 5
```

```yaml
# llm_corpus/pack.yaml — 行业 7 步流水线
agents:
  - id: requirement_agent
    depends_on: []
    step: 1
  - id: compliance_agent          # 行业特有 Agent
    depends_on: [requirement_agent]
    step: 2
  - id: feature_agent
    depends_on: [compliance_agent]
    step: 3
  - id: software_arch_agent
    depends_on: [feature_agent]
    step: 4
  - id: hardware_agent
    depends_on: [software_arch_agent]
    step: 5
  - id: lifecycle_agent           # 行业特有 Agent
    depends_on: [hardware_agent]
    step: 6
  - id: budget_agent
    depends_on: [lifecycle_agent]
    step: 7
```

### 4.2 DAG 动态构建

```
domain Pack 的 pack.yaml agents[]
    │
    ▼
get_agents_dag()
    │
    ├── 读取 agents[] 的 depends_on
    ├── Kahn 拓扑排序（按 step 字段打破平局）
    ├── 环检测：存在环时回退到按 step 排序
    │
    ▼
返回 pipeline_steps + step_view_map + agent_configs + entry_point
    │
    ▼
PipelineDAG._build_graph()
    │
    ├── 为每个 agent 创建 graph node
    ├── 根据 depends_on 构建条件边
    ├── 入口点 = 入度为 0 的节点
    │
    ▼
LangGraph StateGraph（运行时构建，非硬编码）
```

### 4.3 LangGraph 集成

```python
class PipelineDAG:
    """
    LangGraph StateGraph 包装器。
    
    - 从 domain Pack 的 agents 配置动态构建 DAG
    - 条件边：step_by_step 暂停 / batch 自动继续
    - Checkpoint：AsyncSqliteSaver（降级回退 MemorySaver）
    - 子图：重算场景动态构建
    """
    
    def __init__(self, orchestrator, checkpoint_dir=None):
        dag_config = orchestrator.unified_loader.get_agents_dag()
        self.PIPELINE_STEPS = dag_config["pipeline_steps"]
        self.STEP_VIEW_MAP = dag_config["step_view_map"]
        self.agent_configs = dag_config["agent_configs"]
        self.entry_point = dag_config["entry_point"]
        self.graph = self._build_graph()
```

**四种执行模式**：

| 方法 | 模式 | 说明 |
|------|------|------|
| `run_batch()` | 批量 | 一次性跑完全部 Agent |
| `run_step()` | 单步 | 执行第一步后暂停（WAITING_CONFIRM） |
| `continue_from_checkpoint()` | 恢复 | 从 checkpoint 恢复执行下一步 |
| `run_rerun_steps(steps)` | 重算 | 为变更传播构建子图执行 |

---

## 五、Pack 架构 ★ v4.3 重构

### 5.1 设计哲学

**v4.3 模型变更**：从三层继承（abc → base → 行业）改为平级组合（domain + commons）。

```
旧模型（v4.2）：                        新模型（v4.3）：
                                        
abc (语法契约)                          abc (语法契约，不变)
  ↓                                      ↙        ↘
base (通用实现)                       base (commons)  llm_corpus (domain)
  ↓                                 · 架构图/技术栈    · Schema/Rules/Skills
行业 Pack (覆盖 base)                · 通用 Skills     · Knowledge/Templates
                                    · 按名引用        · 完全独立
                                    
                                    ╲        ╱
                                     项目 123
                                   domain_pack = llm_corpus
                                   + 引用 base 资产（可选）
```

**核心原则**：
- **domain Pack**（如 llm_corpus）：领域自包含——提供 Schema、Rules、Skills、Knowledge、Templates、Pricing。零依赖。
- **commons Pack**（如 base）：通用资产提供者——提供架构图、技术栈文档、通用 Skills。被引用，不参与合并。
- **零继承**：domain 和 commons 是平级关系，没有覆盖/继承链。abc 是共同的及格线。
- **按需引用**：domain Pack 通过 `requires_commons: [base]` 声明可以引用 base 的资产，模板中使用 `{{ asset("base:diagrams/software_arch.md") }}` 引用。

### 5.2 pack.yaml 新字段

```yaml
# domain Pack（llm_corpus/pack.yaml）
id: llm_corpus
kind: domain                                    # ★ 新增
requires_commons:                               # ★ 新增
  - base                                        # 可引用 base 的通用资产
agents: [...]
fact_schemas: [...]
skills: {...}
rules: {...}
intent_keywords:                                # ★ 新增：智能更新意图路由
  requirement: ["语料", "规模", "语种", ...]
  feature: ["功能", "标注引擎", ...]

# commons Pack（base/pack.yaml）
id: base
kind: commons                                   # ★ 新增
provides:                                       # ★ 新增：声明提供哪些通用资产
  assets:
    - diagrams/software_arch.md
    - diagrams/system_arch.md
    - diagrams/hardware_arch.md
    - diagrams/network_topo.md
    - tech_stacks/springboot_vue.md
    - tech_stacks/python_fastapi.md
  skills:
    - server_estimator
    - budget_builder
agents: [...]                                    # base 自身也声明 agents（当 domain 用）
fact_schemas: [...]
```

### 5.3 UnifiedLoader 架构

```python
class UnifiedLoader:
    """
    domain+commons 双通道加载器。

    加载顺序：
    1. 加载 abc（形式规约校验）
    2. 加载 domain Pack（Schema/Rules/Skills/Knowledge/Templates/Pricing）
    3. 加载 commons Packs（仅资产和通用 Skills，不参与自动合并）
    """

# 使用方式
loader = UnifiedLoader(
    domain_pack="packs/llm_corpus",      # 领域 Pack（必须）
    commons=["packs/base"],              # 通用资产（可选）
)
loader = UnifiedLoader(domain_pack="packs/base")  # base 可自身当 domain 用
```

### 5.4 合并策略

| 组件类型 | 合并策略 | 逻辑 |
|---------|---------|------|
| **Fact Schema** | domain 独有 | 不合并 commons |
| **Rules** | domain 独有 | 不合并 commons |
| **Templates** | domain 独有 | 不合并 commons |
| **Pricing** | domain 独有 | 不合并 commons |
| **Knowledge** | domain 独有 | 不合并 commons（避免领域污染） |
| **Assets** | commons 提供，按名引用 | `get_asset_path("base:diagrams/software_arch.md")` |
| **Skills** | domain 优先，无则回退 commons | 通过 SkillRegistry 动态加载 |
| **Agent 配置** | domain 独有 | 从 domain pack.yaml 读取 DAG |

### 5.5 Asset 引用 ★ v4.3 新增

模板渲染时，domain Pack 可以引用 commons 的通用资产：

```jinja2
## 软件架构

{{ asset("base:diagrams/software_arch.md") }}

## 技术选型

本项目采用以下技术栈：

{{ asset("base:tech_stacks/springboot_vue.md") }}
```

`Renderer._asset_ref(asset_key)` → `unified_loader.get_asset_path()` → 读取文件内容 → 注入模板。

### 5.6 Skill 接口统一 ★ v4.3 新增

所有 Skills 统一接受 `facts: Dict[str, Any]` 作为入参：

```python
# base skills（通用层）
def storage_calc(facts: Dict[str, Any]) -> Dict[str, Any]:
    data_volume_per_unit = facts.get("data_volume_per_unit", 0)
    unit_count = facts.get("unit_count", 0)
    redundancy = facts.get("redundancy", 1.5)
    ...

def gpu_estimator(facts: Dict[str, Any]) -> Dict[str, Any]:
    camera_count = facts.get("camera_count", 0)
    ai_analysis = facts.get("ai_analysis", False)
    ...

# Pack skills（行业层）
def calculate_storage(facts: Dict[str, Any]) -> Dict[str, Any]:
    data_volume_tb = float(facts.get("语料总规模TB", 100))
    return storage_calc({"data_volume_per_unit": data_volume_tb, ...})

def estimate_gpu(facts: Dict[str, Any]) -> Dict[str, Any]:
    corpus_volume = facts.get("语料总规模TB", 0)
    ...
```

Agent 调用 Skill 统一路径：
```python
def _call_domain_skill(self, skill_name: str, facts: dict) -> dict:
    skill_func = self.skill_registry.get(skill_name)
    return skill_func(facts)  # 单一接口，无适配层
```

### 5.7 智能更新意图路由 ★ v4.3 新增

意图关键词从 Pack config 加载，不再硬编码在 Orchestrator 中：

```python
class Orchestrator:
    def _get_intent_keywords(self) -> dict:
        base = {
            "architecture": ["架构", "技术选型", ...],
            "hardware": ["硬件", "GPU", ...],
            "budget": ["预算", "费用", ...],
        }
        # 从 domain Pack 加载行业特化关键词
        pack_kw = self.unified_loader.get_pack_config().get("intent_keywords", {})
        return {**base, **pack_kw}
```

### 5.8 合规标准 ★ v4.3 新增

行业标准从 Pack rules 加载，不再硬编码在 Agent 代码中：

```yaml
# llm_corpus/rules/compliance_rules.yaml
- id: industry_standards
  name: 行业标准映射
   standards:
     大模型语料:
       - "GB/T 42755-2023 人工智能 面向机器学习的数据标注规程"
       - "GB/T 41867-2022 信息技术 人工智能 术语"
       - "GB/T 42018-2022 信息技术 人工智能 平台计算资源规范"
       - "生成式AI服务管理办法"
       - "数据安全法"
       - "个人信息保护法"
```

```python
class ComplianceAgent:
    def _load_industry_standards(self, industry: str) -> list:
        rules = self.unified_loader.get_rules("compliance_rules")
        for rule in rules:
            if rule.get("id") == "industry_standards":
                return rule.get("standards", {}).get(industry, [])
        return ["GB/T 19101-2020", "数据安全法", "个人信息保护法"]
```

### 5.9 Agent 清毒 ★ v4.3 新增

**原则**：Agent 代码中不允许出现任何行业特定字符串（摄像头、语料、视频、监控等）。Agent 只通过 `unified_loader.get_rules()` 和 `SkillRegistry` 获取领域行为。

**FeatureAgent**：删除 `camera_count`/`corpus_volume` 领域探测、`_apply_hardcoded_feature_rules()` 硬编码回退函数、领域字段引用。

```python
# v4.3：纯规则驱动
pack_rules = self.unified_loader.get_rules("feature_rules")
if not pack_rules:
    raise ValueError("当前 domain Pack 未定义功能规则")
must_have_features, should_have_features = self._apply_pack_feature_rules(pack_rules, req, project)
```

**HardwareAgent**：删除 50 行 `is_corpus_domain` 快捷路径、150 行摄像头 BOM 硬编码。统一通过 `_call_domain_skill()` 调用 Pack Skill。

```python
# v4.3：纯 Skill 驱动
storage_result = self._call_domain_skill("storage_calc", req)
gpu_result = self._call_domain_skill("gpu_estimator", req)
server_result = self._call_domain_skill("server_estimator", req)
```

### 5.10 目录结构

```
packs/
├── abc/                          # 形式规约（meta-schemas）
│   ├── pack.yaml                 # kind 未声明（特殊层）
│   └── meta/                     # pack-manifest.yaml (v2.0)、fact-schema.yaml 等
├── base/                         # commons Pack（通用资产）
│   ├── pack.yaml                 # kind: commons, provides: {assets, skills}
│   ├── fact_schema/              # 通用 Schema（英文，可选）
│   ├── rules/                    # 通用规则
│   ├── skills/                   # 通用 Skills（facts: dict 接口）
│   ├── knowledge/                # 通用知识（可选）
│   ├── templates/                # 通用模板（可选）
│   ├── config/                   # 通用 TOC 配置
│   ├── diagrams/                 # ★ 通用架构图（Mermaid）
│   │   ├── software_arch.md
│   │   ├── system_arch.md
│   │   ├── hardware_arch.md
│   │   └── network_topo.md
│   └── tech_stacks/              # ★ 通用技术栈
│       ├── springboot_vue.md
│       └── python_fastapi.md
└── llm_corpus/                   # domain Pack（大模型语料）
    ├── pack.yaml                 # kind: domain, requires_commons: [base]
    ├── fact_schema/              # 行业 Schema（中文）
    ├── rules/                    # 行业规则（feature_rules、hardware_rules、budget_rules、compliance_rules）
    ├── skills/                   # 行业 Skills（facts: dict 接口）
    ├── knowledge/                # 行业知识
    ├── templates/                # 行业报告模板
    ├── config/                   # 行业 TOC 配置
    └── pricing.json              # 行业定价
```

### 5.11 实施结果 ★ v4.3

| 指标 | v4.2 | v4.3 |
|------|------|------|
| Pack 模型 | abc→base→行业 继承 | domain+commons 平级组合 |
| Agent 行业硬编码 | feature_agent: 摄像头/语料探测 | 零行业字符串 |
| Skill 接口 | 命名参数（camera_count, bitrate_mbps） | 统一 facts: dict |
| runtime/skills/ | 11 个废弃文件 | 已删除 |
| 意图路由 | Orchestrator 硬编码视频监控关键词 | Pack config 加载 |
| 合规标准 | Agent 代码硬编码 | Pack rules 加载 |
| 模板资产引用 | 不支持 | {{ asset("base:diagrams/...") }} |
| 测试基线 | 73 | **182** |

### 5.12 架构权衡 ★ v4.3

v4.3 从三层继承改为平级组合，带来根本性的 trade-off：

| 维度 | 旧模型（v4.2 三级继承） | 新模型（v4.3 平级组合） |
|------|------------------------|------------------------|
| 领域纯隔离 | 规则/Knowledge 可能从 base 泄漏到行业 | 零泄漏——domain 完全自包含 |
| 新 Pack 制作效率 | 只写差异（覆盖 3 个 Schema + 2 个 Skill），半天可完成 | 需要从零编写全部配置文件（Schema + Rules + Skills + Knowledge + Templates + Pricing），工作量与行业复杂度正相关 |
| 跨领域复用 | 通过继承自动获得 base 的通用功能 | 需显式 `requires_commons` + 模板中 `{{ asset() }}` 按名引用 |
| 维护安全 | 改 base 可能静默破坏所有行业 Pack | 改 base 只影响资产引用，domain Pack 不受影响 |
| 调试难度 | 字段来源不透明（来自 base 还是行业覆盖？）| 字段来源唯一（全部在 domain Pack 内） |
| 商业分发 | 行业 Pack 无法独立分发（依赖 base） | domain Pack 可独立打包分发 |

**设计选择**：v4.3 牺牲了「新 Pack 制作效率」，换取了「隔离纯度、维护安全、独立分发」。这是有意识的选择——对于可研报告这种商业场景，领域隔离的安全性和 Pack 的独立分发权比快速制作新 Pack 更重要。

### 5.13 Pack 开发与测试

验证一个行业 Pack 是否可用的最低操作流程：

**1. 合规性验证**：检查 Pack 是否符合 abc 规约。
```bash
cd mvp && ../venv/bin/python -c "
from runtime.pack_validator import PackValidator
v = PackValidator()
r = v.validate('packs/{industry}')
print(f'Passed: {r.passed}, Errors: {r.error_count}')
"
```

**2. 最小功能验证**：启动 CLI 输入行业需求，确认 FeatureAgent / HardwareAgent 不报错。
```bash
cd mvp && ../venv/bin/python cli.py --pack packs/{industry} --project test
```

P0 级别检查：`rules/feature_rules.yaml` 必须存在且包含至少一条 `condition: "true"` 的规则——缺少则 FeatureAgent 直接抛出 `ValueError`。

**3. 端到端回归**：确认基线测试不退化。
```bash
cd mvp && ../venv/bin/python -m pytest tests/ -q
```

**4. 新增 Pack 专用测试**：在 `tests/` 下新增 `test_pack_{industry}.py`，覆盖该 Pack 的 Schema 加载、Rules 评估、端到端 DAG 执行。

---

## 六、基于 Fact 的 Context/Memory 机制

### 6.1 设计哲学

**一篇可研报告的 Fact 总量约 1500-2000 tokens，完全在 LLM 上下文范围内。不需要摘要，全量注入即可。**

```
传统做法：                            本系统做法：
  Agent 需要"记忆"                     Agent 不需要"记忆"
  长期 Memory + 短期 Memory            Runtime 精确注入全部上下文
  摘要 → 信息丢失                       全量 → 信息完整
  LLM 自行判断缺什么                     Runtime 确保不缺任何东西
```

**LLM 不需要"记忆"——所有上下文由 Runtime 精确注入。**

### 6.2 FactContextBuilder

```python
class FactContextBuilder:
    """
    将 FactStore 中的 Fact 序列化为结构化文本上下文。
    
    核心设计：全量加载，不摘要。
    """
    
    def __init__(self, fact_store, unified_loader=None):
        self.fs = fact_store
        self.unified_loader = unified_loader
        # 动态构建映射：从 domain Pack Schema 构建
        self._section_order, self._section_names, self._section_to_step, self._downstream_map = \
            build_section_mappings(unified_loader)
```

### 6.3 三种上下文构建模式

| 模式 | 方法 | 用途 | 内容 |
|------|------|------|------|
| 全量上下文 | `build_full_context()` | Agent 生成时注入 | 所有有数据的 Section，按 DAG 顺序 |
| 更新上下文 | `build_update_context(user_input)` | 用户修改时分析 | 全量 + DAG 状态 + 修改历史 |
| 差异摘要 | `build_diff_summary(old, new)` | 变更传播通知 | 变更字段路径列表 |

### 6.4 上下文注入时机

```
Agent 执行前
    │
    ├── 1. 从 FactStore 读取该 Agent 有权访问的 Fact
    ├── 2. 从 UnifiedLoader 获取行业知识（get_knowledge_for_agent）
    ├── 3. 从 SkillRegistry 获取可用 Skill
    ├── 4. 构建 FactContext（全量 Fact 序列化）
    ├── 5. 组装 LLM Prompt = System（角色+约束）+ Context（Fact+知识）+ User（输入）
    │
    ▼
    LLM 在完整数据框架内"填空"，不靠记忆
```

### 6.5 Schema 校验时机

| 时机 | 校验内容 |
|------|---------|
| Patch 提交时 | Schema 静态校验（字段类型、范围、枚举）—— SchemaValidator 从 UnifiedLoader 加载 domain Pack 的 Schema |
| 传播完成时 | 跨节点一致性（GPU 数量硬件 vs 预算） |
| 交付前 | 全量校验（完整性 + 一致性 + 合规 + 合理性） |

---

## 七、动态传播机制

### 7.1 设计哲学

**传播链从 Schema 的 `affects` 配置动态构建，而非硬编码。**

这意味着：行业 Pack 新增一个 Schema（如 `AISpec`），只需在 Schema YAML 中声明 `affects`，传播链自动工作，无需改任何源码。

### 7.2 Schema affects 配置

每个 Fact Schema YAML 可以声明 `affects` 字段：

```yaml
# fact_schema/FeatureList.yaml
affects:
  - SoftwareArch    # 功能列表变化 → 软件架构需重算
  - HardwareSpec    # 功能列表变化 → 硬件规格需重算
  - Budget          # 功能列表变化 → 预算需重算
```

```yaml
# packs/llm_corpus/fact_schema/AIMLEngineSpec.yaml
affects:
  - HardwareSpec    # AI 引擎规格 → GPU 配置
  - Budget          # AI 相关费用重算
```

### 7.3 build_section_mappings() 动态构建

```python
def build_section_mappings(unified_loader=None):
    """
    从 UnifiedLoader 加载的 domain Pack Schema 动态构建 Section 映射。
    
    :return: (section_order, section_names, section_to_step, downstream_map)
    """
    if not unified_loader:
        return SECTION_ORDER, SECTION_NAMES, SECTION_TO_STEP, DOWNSTREAM_MAP
    
    # 从 domain Pack Schema 列表构建
    # 已知 Section 用已有映射，新增 Section 按 affects 推断
```

**未知 Schema 的推断逻辑**：
1. 优先读取 Schema 的 `agent` 字段（显式声明，最可靠）
2. 无 `affects` → 叶子节点，不影响其他 Section
3. `affects` 含 `HardwareSpec` → `software_arch_agent`（中间节点）
4. `affects` 只含 `Budget` → `hardware_agent`（硬件层）
5. 其他 → `software_arch_agent`（安全回退）

### 7.4 传播链的消费方

所有需要传播链的组件，统一通过 `build_section_mappings(unified_loader)` 获取动态映射：

| 消费方 | 获取方式 |
|--------|---------|
| `FactContextBuilder` | `build_section_mappings(unified_loader)` → `self._downstream_map` |
| `UpdateAnalyzer` | `build_section_mappings(unified_loader)` → `self._section_to_step` |
| `Orchestrator._determine_rerun_steps()` | `build_section_mappings(self.unified_loader)` |
| `BidirectionalPropagator` | `_build_fact_type_to_agent(unified_loader)` + `_build_agent_downstream(unified_loader)` |

### 7.5 传播执行流程

```
用户发起修改
    │
    ├─ UpdateAnalyzer 分析
    │   ├─ 规则快速匹配（高置信度，不调 LLM）
    │   │   ├─ 否定式开关："不需要等保" → TOGGLE_OPTION
    │   │   └─ 数值调整："语料总规模改成500TB" → ADJUST_PARAM
    │   └─ LLM 深度分析（模糊场景，全量 Fact Context 注入）
    │
    ├─ 输出结构化修改指令
    │   {changes, affected_steps, affected_sections, clear_sections}
    │
    └─ Orchestrator._apply_incremental_update()
        │
        ├─ Step 1: 增量应用变更到 FactStore（不再 clear_section）
        ├─ Step 2: _determine_rerun_steps() 确定需要重算的 Agent
        │   └─ 使用动态 DOWNSTREAM_MAP 计算下游
        ├─ Step 3: 重置受影响步骤为 PENDING
        └─ Step 4: 执行重算
            ├─ step_by_step: 执行第一个 → WAITING_CONFIRM
            └─ batch: PipelineDAG.run_rerun_steps() 子图执行
```

### 7.6 增量修改

**增量修改——只改用户提到的字段，其他字段保持不变，只重跑受影响的下游 Agent。**

| 场景 | 增量修改行为 |
|------|------------|
| 调整语料规模 | 只改 `语料总规模TB` → 下游 Agent 增量重算 |
| 取消价值对齐 | 只改 `是否需要价值对齐`=false → 下游增量重算 |
| 增加功能点 | 追加到 `features[]` → 下游增量重算 |

---

## 八、Smart Update 意图路由

### 8.1 核心流程

```
用户输入
    │
    ▼
UpdateAnalyzer.analyze(user_input)
    │
    ├─ Step 1: 判断生成/修改（检查 RequirementList 是否有数据）
    │   └─ is_generation=True → 走 start() 首次生成
    │   └─ is_generation=False → 走修改路径
    │
    ├─ Step 2: 构建全量 Fact Context（build_update_context）
    │
    ├─ Step 3: 规则快速匹配（高置信度场景，不调 LLM）
    │   ├─ 否定式开关："不需要价值对齐" → TOGGLE_OPTION
    │   └─ 数值调整："语料总规模改成500TB" → ADJUST_PARAM
    │
    └─ Step 4: LLM 深度分析（模糊场景）
        └─ 全量 Fact Context + 修改规则 → 结构化修改指令
```

### 8.2 修改类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `modify_field` | 修改某个字段值 | "安全等级改为高" |
| `add_feature` | 添加功能点 | "增加智能标注能力" |
| `remove_feature` | 删除功能点 | "取消毒性检测" |
| `adjust_param` | 调整参数 | "语料总规模改成500TB" |
| `toggle_option` | 开关选项 | "不需要价值对齐" |
| `global_rebuild` | 全局重建 | "重新来过" |

---

## 九、Agent 工作流

### 9.1 核心约束：单向补充，禁止回溯

每一步 Agent 只能补充（expand）内容，不能删除上游 Fact 中的内容。

**通用 5 步流水线（base）**：
```
需求 Agent → FactContext 注入（无上游数据）→ RequirementList + Project
功能 Agent → FactContext 注入（RequirementList）→ FeatureList
架构 Agent → FactContext 注入（RequirementList + FeatureList）→ SoftwareArch
硬件 Agent → FactContext 注入（全量上游）→ HardwareSpec
预算 Agent → FactContext 注入（全量 Fact）→ Budget
```

**行业扩展 7 步流水线（llm_corpus）**：
```
需求 Agent → RequirementList + Project
合规 Agent → Compliance
功能 Agent → FeatureList
架构 Agent → SoftwareArch + AuthDesign + DRDesign + NetworkDesign
硬件 Agent → HardwareSpec + NetworkTopo + StorageSpec
生命周期 Agent → ProjectLifecycle
预算 Agent → Budget
```

> 注：不同 Pack 可声明不同的 Agent 数量和依赖关系，DAG 由 pack.yaml 的 `agents[].depends_on` 动态构建，非硬编码。

### 9.2 两种工作模式

| 特性 | 步步确认模式 | 批量执行模式 |
|------|-------------|-------------|
| 暂停次数 | N 次（每步） | 0 次 |
| 状态机 | PENDING → RUNNING → WAITING_CONFIRM → DONE | PENDING → RUNNING → DONE |
| 适合场景 | 新手用户、高风险项目 | 快速迭代、老用户 |
| LangGraph 实现 | 条件边返回 "pause" | 条件边返回 "continue" |

### 9.3 串行执行顺序

```
Step 1: 需求 Agent（RequirementAgent）
    ├─ 输入：用户自然语言描述
    ├─ Context：无上游数据
    ├─ Skill：无
    ├─ 输出：RequirementList + Project
    └─ 依赖：无

Step 1b: 合规 Agent（ComplianceAgent）★ llm_corpus 等 Pack 可选
    ├─ 输入：FactContext（RequirementList + Project）
    ├─ Skill：compliance_check
    ├─ 输出：Compliance
    └─ 依赖：Step 1

Step 2: 功能列表 Agent（FeatureAgent）
    ├─ 输入：FactContext（RequirementList + Compliance）
    ├─ Skill：feature_dependency
    ├─ 输出：FeatureList
    └─ 依赖：Step 1（或 Step 1b）

Step 3: 软件架构 Agent（SoftwareArchAgent）
    ├─ 输入：FactContext（RequirementList + FeatureList）
    ├─ Skill：auth_design / concurrent_design / dr_design / network_design
    ├─ 输出：SoftwareArch + AuthDesign + DRDesign + NetworkDesign
    └─ 依赖：Step 2

Step 4: 硬件/网络拓扑 Agent（HardwareAgent）
    ├─ 输入：FactContext（全量上游）
    ├─ Skill：storage_calc / bandwidth_calc / gpu_estimator / server_estimator
    ├─ 输出：HardwareSpec + NetworkTopo + StorageSpec
    └─ 依赖：Step 3

Step 4b: 生命周期 Agent（LifecycleAgent）★ llm_corpus 等 Pack 可选
    ├─ 输入：FactContext（全量上游）
    ├─ Skill：risk_assessor
    ├─ 输出：ProjectLifecycle
    └─ 依赖：Step 4

Step 5: 预算 Agent（BudgetAgent）
    ├─ 输入：FactContext（全量 Fact）
    ├─ Skill：budget_builder（× price_coefficient）
    ├─ 输出：Budget
    └─ 依赖：Step 4（或 Step 4b）
```

---

## 十、Fact Store 与存储

### 10.1 文件化存储（零外部依赖）

```
projects/{project_id}/
    ├── fact_graph.json       # 全量 Fact 快照（原子写入）
    ├── patch_log.jsonl       # append-only WAL 日志
    ├── dag_state.json        # DAG 节点执行状态
    ├── section_ctx/          # 每节点执行上下文
    ├── views/                # Fact View（每步产物，供确认）
    │   ├── requirement.json
    │   ├── feature.json
    │   ├── software_arch.json
    │   ├── hardware.json
    │   └── budget.json
    └── output/               # 最终交付文档
        └── 可研报告_v1.md
```

### 10.2 Fact View 交互

每个 Agent 完成后，生成 Fact View 供用户确认：

```json
{
  "step": "feature",
  "status": "PENDING_CONFIRM",
  "updated_at": "2026-04-23T10:00:00",
  "facts": { ... }
}
```

---

## 十一、Fact Schema 中文字段设计

### 11.1 设计哲学

**Fact Schema 字段名使用中文命名，使 LLM 生成 fact 指令更精准、更泛化。**

核心洞察：
- LLM 对中文字段名的理解更直觉，"语料总规模TB"比"corpus_volume_tb"语义更明确
- 用户输入也是中文，中文字段减少翻译损失
- 中文枚举值（如"文本/图像/视频/音频" vs "text/image/video/audio"）与行业术语一致

### 11.2 base vs domain Pack Schema 字段命名策略

| Schema 版本 | 字段命名 | 原因 |
|-------------|---------|------|
| base（commons） | 英文 | 通用场景，不绑定行业，如 `scale`、`concurrent_users` |
| llm_corpus（domain） | 中文 | 行业特化，绑定行业语义，如 `语料总规模TB`、`语种数量` |

### 11.3 示例对比

```yaml
# base/fact_schema/RequirementList.yaml（英文，通用型）
fields:
  scale:
    type: integer
    description: 系统规模（如设备数量、用户数等）
  concurrent_users:
    type: integer
    description: 并发用户数

# llm_corpus/fact_schema/RequirementList.yaml（中文，行业特化）
fields:
  语料总规模TB:
    type: number
    description: 语料数据总规模（TB）
    min: 10
    max: 10000
  语种数量:
    type: integer
    description: 覆盖语种数量
  是否需要智能标注:
    type: boolean
    description: 是否需要智能标注
  是否需要价值对齐:
    type: boolean
    description: 是否需要价值对齐（RLHF）
```

### 11.4 UpdateAnalyzer 规则匹配适配

中文字段名使规则匹配更自然：

```python
# 否定式开关：直接用中文字段名
([["不需要价值对齐", "取消价值对齐"], TOGGLE_OPTION, "RequirementList", {"是否需要价值对齐": False})
(["不需要AI", "取消AI"],   TOGGLE_OPTION, "RequirementList", {"是否需要智能标注": False})

# 数值调整：中文字段名与用户输入一致
(r"语料.*?(\d+).*?TB", "RequirementList", "语料总规模TB", int)
(r"语种.*?(\d+).*?个", "RequirementList", "语种数量", int)
```

---

## 十二、Skills 体系

### 12.1 两类 Skills

| 类型 | 特征 | 示例 |
|------|------|------|
| **计算型** | 输入数字 → 输出推算结果，确定性强 | storage_calc / bandwidth_calc / gpu_estimator / budget_builder |
| **知识型** | 功能点判断规则，规则 YAML + Python 实现 | auth_design / concurrent_design / dr_design / network_design / feature_dependency |

### 12.2 Skill 分层注册

```python
# base skill: packs/base/skills/storage_calc.py → storage_calc(facts: dict)
# Pack skill: packs/llm_corpus/skills/storage_calc.py → calculate_storage(facts: dict)

registry = SkillRegistry(pack_loader)
result = registry.call("storage_calc", facts={"语料总规模TB": 1000})
# 自动使用 Pack 版本（如有），否则使用 base 版本
```

---

## 十三、渲染体系

### 13.1 三层渲染

| 层 | 产物 | 时机 | LLM 参与 |
|----|------|------|---------|
| Fact View | `views/{step}.json` | 每个 Agent 完成后 | 否 |
| TOC-Driven Renderer | 按 `config/chapters/*.yaml` 动态构建章节，按 `fact_bindings` 注入数据 | 编译时 | 否（纯数据编译） |
| Legacy Renderer | Jinja2 平面模板 | 无 TOC 配置时回退 | 否（纯数据编译） |

### 13.2 TOC 驱动渲染（v4.0+）

TOC 驱动渲染从 `config/chapters/*.yaml` 动态构建章节结构，每个 Section 声明 `fact_bindings` 指定绑定的 Fact 类型：

```yaml
# config/chapters/overview.yaml
chapter_number: 1
chapter_title: "项目概述"
sections:
  - section_number: "1.1"
    section_title: "项目概况"
    sub_sections:
      - number: "1.1.1"
        title: "项目名称与目标"
    fact_bindings: ["Project"]
```

**空节处理**：
- 有 `fact_bindings` 但无对应数据的 Section → 自动隐藏
- 无 `fact_bindings` 且无子节的 Section → 自动隐藏
- 无 `fact_bindings` 但有叙事内容的 Section → 注入 NarrativeAgent 生成的叙事

**表格渲染**：
- 有 `table_definitions` 配置 → 使用 `field_mapping` 将英文字段映射为中文列名
- 无 `table_definitions` → 自动检测字段类型，通过 Schema 的 `description` 查找中文标签，回退到内置中文标签映射

### 13.3 叙事生成（NarrativeAgent）

对 `fact_bindings: []` 的章节，NarrativeAgent 基于全量 Fact 上下文，通过 LLM 生成叙事性段落内容（每节约 200-500 字），存储于 Fact Store 的 `_narratives` 中，渲染时自动注入。

### 13.4 模板优先级

```
domain Pack 模板 > Legacy 内置模板
```

---

## 十四、Pack DSL 规范

### 16.1 Fact Schema 增加 affects 配置

```yaml
# fact_schema/RequirementList.yaml（llm_corpus）
fact_type: RequirementList
description: 需求列表
agent: requirement_agent
fields:
  语料总规模TB: {type: number, min: 10, max: 10000, required: true}
  语种数量: {type: integer, min: 1, required: true}
  是否需要智能标注: {type: boolean, required: true}
  # ...

affects:
  - HardwareSpec
  - Budget
```

### 16.2 pack.yaml 支持 Agent 知识分配

```yaml
agents:
  - id: feature_agent
    display_name: 功能规划专家
    knowledge:
      - best_practices
      - industry_standards
```

### 16.3 pack.yaml 规范 ★ v4.3 更新

```yaml
# domain Pack — 行业领域
id: llm_corpus
kind: domain
version: "2.0.0"
requires_commons:                                # ★ v4.3
  - base
agents:
  - id: requirement_agent
    depends_on: []
    step: 1
  - id: compliance_agent                         # 行业特有 Agent
    depends_on: [requirement_agent]
    step: 2
  - id: feature_agent
    depends_on: [compliance_agent]
    step: 3
  # ...
rules:
  feature_rules: rules/feature_rules.yaml         # ★ v4.3：统一命名
  hardware_rules: rules/hardware_rules.yaml
  budget_rules: rules/budget_rules.yaml
  compliance_rules: rules/compliance_rules.yaml
intent_keywords:                                  # ★ v4.3：智能更新意图路由
  requirement: ["语料", "规模", "语种", "标注", "等保", ...]
  feature: ["功能", "增加", "删除", "标注引擎", ...]

# commons Pack — 通用资产
id: base
kind: commons
provides:                                         # ★ v4.3
  assets:
    - diagrams/software_arch.md
    - diagrams/system_arch.md
    - diagrams/hardware_arch.md
    - diagrams/network_topo.md
    - tech_stacks/springboot_vue.md
    - tech_stacks/python_fastapi.md
  skills:
    - server_estimator
    - budget_builder
```

**合并规则（v4.3）**：
- domain Pack 的 `requires_commons` 声明可引用的 commons
- commons Pack 的 `provides` 声明可被引用的资产
- commons 资产不自动合并到 domain Schema/Rules/Knowledge 中
- 模板通过 `{{ asset("base:diagrams/software_arch.md") }}` 按名引用

---

## 十五、系统关键原则

1. **声明式优于命令式**：执行流程由配置声明，非代码硬编码
2. **domain+commons 平级组合** ★ v4.3：domain Pack 和 commons Pack 平级独立，零继承。domain 提供 Schema/Rules/Skills，commons 提供通用资产按名引用
3. **事实驱动，而非意图猜测**：全量 Fact Context 注入 LLM，由事实决定修改方案
4. **增量修改优先**：改字段值而非 clear_section，保留未变更数据
5. **传播链动态构建**：从 Schema `affects` 配置驱动，新增 Schema 无需改源码
6. **中文字段泛化指令**：行业 Schema 用中文字段名，LLM 生成指令更精准
7. **LLM 不产生最终内容**，只产生结构化变更指令
8. **文档是编译产物**，Fact Graph → Renderer → Word
9. **Runtime 强制规则**，不靠 Prompt，靠 PermissionGuard + Validator
10. **Patch Log 是命脉**，append-only JSONL，任何时刻可回放重建
11. **Pack 是核心资产**，行业壁垒和商业价值所在
12. **变更只传播，不回溯**，下游重算，上游 Fact 不因下游结果倒推修改
13. **Agent 单向补充，禁止删上游**
14. **Fact Context 全量注入**：~1500-2000 tokens，在 LLM 上下文范围内，不摘要
15. **Agent 代码零行业假设** ★ v4.3：Agent 源码不包含对任何特定行业的硬编码分支（如 if 语料 elif 摄像头）。领域字段名从 Pack config 加载，Agent 只做通用数据操作。Agent 处理的 Fact 数据中包含行业字段名（如 `语料总规模TB`）是合法行为——这是数据，不是代码假设。
16. **两种工作模式适应不同场景**：步步确认 vs 批量执行
17. **存储零外部依赖**：Fact Store / Patch Log / DAG State 全部文件化
18. **Skill 接口统一** ★ v4.3：所有 Skill 接受 `facts: Dict[str, Any]`，Agent 通过 SkillRegistry 单一接口调用
19. **意图路由从 Pack 配置加载** ★ v4.3：智能更新的关键词和领域示例从 Pack config 读取，不硬编码在 Orchestrator 中
20. **通用资产按名引用** ★ v4.3：commons Pack 资产通过 `{{ asset("base:diagrams/...") }}` 在模板中引用

---

*本文档描述 v4.0 当前版本的架构设计与实现。历史版本变更请参见"零、版本历史"。*
