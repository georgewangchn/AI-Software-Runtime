#!/bin/bash
# ASR 启动脚本示例
# 复制此文件并修改为你自己的路径和模型配置

# ---- 路径配置 ----
DEVDIR=/path/to/your/project   # 修改为你的项目目录
ASR_ROOT=$(cd "$(dirname "$0")" && pwd)

# ---- LLM 模型配置（读取自 .env，或在此处直接设置）----
# 如果已配置 .env，以下变量可省略（loader.py 会自动加载）
# export FEASIBILITY_LLM_API_BASE=http://your-llm-host:8000/v1
# export FEASIBILITY_LLM_API_KEY=your-api-key
# export FEASIBILITY_LLM_MODEL=your-model-name
# export FEASIBILITY_LLM_CONTEXT=131072

# ---- ASR 运行参数 ----
export ASR_OPENCODE_TIMEOUT="144000"
export ASR_VERBOSE="1"

cd "$ASR_ROOT"

# 启动 ASR（将 DESIGN.md 复制到目标项目目录后运行）
# cp "$DEVDIR/DESIGN.md" "$DEVDIR/your_project/DESIGN.md"
python -m asr.cli.main run --project "$DEVDIR/your_project" --max-iterations 20
