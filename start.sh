#!/bin/bash

DEVDIR=/Users/siidt/Documents/siicode/asr/demo_dev
export ASR_OPENCODE_TIMEOUT="14400"

cd /Users/siidt/Documents/siicode/asr

# 准备开发工作区
rm -rf ".runtime"
cd "$DEVDIR/asr_data" && rm -rf *
cd /Users/siidt/Documents/siicode/asr
cp "$DEVDIR/DESIGN.md" "$DEVDIR/asr_data/DESIGN.md"

# 启动 ASR
python -m asr.cli.main run --project "$DEVDIR/asr_data" --max-iterations 10
