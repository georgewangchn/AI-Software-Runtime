#!/bin/bash
# source venv/bin/activate

DEVDIR=/app/dev/asr/demo_dev
export ASR_OPENCODE_TIMEOUT="7200"

cd /app/dev/asr

# 准备开发工作区
rm -rf ".runtime"
rm -rf "$DEVDIR/asr2" && mkdir -p "$DEVDIR/asr2"
cp "$DEVDIR/DESIGN.md" "$DEVDIR/asr/DESIGN.md"
git init
git add .
git config user.name "siidt"
git config user.email "1"
git commit -m "init asr2 workspace"

# 启动 ASR
python -m asr.cli.main run --project "$DEVDIR/asr2" --max-iterations 10
