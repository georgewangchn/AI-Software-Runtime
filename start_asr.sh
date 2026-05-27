#!/bin/bash

DEVDIR=/app/dev/asr/demo_dev
export ASR_OPENCODE_TIMEOUT="7200"

cd /app/dev/asr

# 准备开发工作区
rm -rf ".runtime"
rm -rf "$DEVDIR/asr" && mkdir -p "$DEVDIR/asr"
cp "$DEVDIR/DESIGN.md" "$DEVDIR/asr/DESIGN.md"

# 启动 ASR
python -m asr.cli.main run --project "$DEVDIR/asr" --max-iterations 10
