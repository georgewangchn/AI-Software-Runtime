#!/bin/bash
set -euo pipefail

source venv/bin/activate
DEVDIR="/Users/siidt/Documents/siicode/asr/demo_dev"
WORKDIR="$DEVDIR/opencode"
MODEL="local/qwen3-next-80b-a3b-instruct"
DESIGN="$DEVDIR/可研报告编译器设计方案 v4.0.md"

# 初始化工作区
rm -rf "$WORKDIR" && mkdir -p "$WORKDIR"
cp "$DESIGN" "$WORKDIR/DESIGN.md"
cd "$WORKDIR" && git init -q && git add -A && git commit -q -m "init"

PROMPT="1. 读取 DESIGN.md 了解系统设计
2. 根据设计完成一个清晰独立的功能开发（增量）
3. git add -A && git commit -m 'done'
4. 回复末尾输出 ### DONE"

SESSION_ID="test01"

for i in $(seq 1 5); do
  echo "========== Iter $i/5 =========="

  if [ -z "$SESSION_ID" ]; then
    output=$(opencode run \
      --model "$MODEL" \
      --dangerously-skip-permissions \
      --format json \
      --dir "$WORKDIR" \
      "$PROMPT" 2>/dev/null)
  else
    output=$(opencode run \
      --model "$MODEL" \
      --dangerously-skip-permissions \
      --format json \
      --session "$SESSION_ID" \
      --continue \
      --dir "$WORKDIR" \
      "$PROMPT" 2>/dev/null)
  fi

  if [ -z "$SESSION_ID" ]; then
    SESSION_ID=$(echo "$output" | python3 -c "import sys,json; print(json.loads(sys.stdin.readline()).get('sessionID',''))" 2>/dev/null || true)
    echo "Session: $SESSION_ID"
  fi

  cd "$WORKDIR"
  git add -A 2>/dev/null
  if git diff --cached --quiet 2>/dev/null; then
    echo "  无变更"
  else
    git commit -q -m "iter-$i" 2>/dev/null && echo "  committed"
  fi
done

echo "完成。工作目录：$WORKDIR"
