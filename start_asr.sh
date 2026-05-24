
source venv/bin/activate
DEVDIR=/Users/siidt/Documents/siicode/asr/demo_dev

cd /Users/siidt/Documents/siicode/asr
# 1. 准备开发工作区（首次）
rm -rf "$DEVDIR/asr" && mkdir -p "$DEVDIR/asr"
cp "$DEVDIR/可研报告编译器设计方案 v4.0.md" "$DEVDIR/asr/DESIGN.md"
# 2. 启动 ASR（Dev Mode，10 轮）
rm -rf .runtime/
python -m asr.cli.main run --project "$DEVDIR/asr" --max-iterations 5
Dev Mode 下 BuilderAgent 独占 10 轮，跳过 Tester/Analyzer。普通模式去掉 ASR_DEV_MODE=1。
