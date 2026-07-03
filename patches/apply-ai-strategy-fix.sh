#!/usr/bin/env bash
# ================================================================
# apply-ai-strategy-fix.sh
#
# 修复 AI 策略生成提示词文档缺失问题。
# 在 git pull 拉取最新代码后运行此脚本即可重新应用修复。
#
# 问题: .dockerignore 排除了 docs/，Docker 容器中 strategy-guide.md
# 和 strategy-builder-step*.md 不可用，导致 LLM 提示词残缺，
# AI 生成的策略缺少 basic_filter/scoring/filter() 等必要结构。
#
# 修复:
#   1. 复制 docs/*.md → backend/app/strategy/prompts/（运行时加载）
#   2. 应用 patch 修改 Python 代码路径（__file__.parent/prompts/）
# ================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_FILE="$PATCH_DIR/ai-strategy-docs.patch"
PROMPTS_DIR="$ROOT/backend/app/strategy/prompts"

echo "==> 1/3 创建 prompts 目录"
mkdir -p "$PROMPTS_DIR"

echo "==> 2/3 复制运行时文档"
for f in strategy-guide.md strategy-builder-step1.md strategy-builder-step2.md; do
    src="$ROOT/docs/$f"
    dst="$PROMPTS_DIR/$f"
    if [ -f "$src" ]; then
        cp "$src" "$dst"
        echo "     ✓ $f ($(wc -c < "$src") bytes)"
    else
        echo "     ⚠ 源文件不存在: $src，跳过"
    fi
done

echo "==> 3/3 应用代码路径 patch"
if [ -f "$PATCH_FILE" ]; then
    cd "$ROOT"
    if git apply --check "$PATCH_FILE" 2>/dev/null; then
        git apply "$PATCH_FILE"
        echo "     ✓ patch 已应用"
    else
        echo "     ⚠ patch 无法直接应用（可能已应用或代码已变化）"
        echo "       手动修改以下文件即可:"
        echo "       - backend/app/strategy/ai_generator.py:17"
        echo "         GUIDE_PATH = Path(__file__).resolve().parent / \"prompts\" / \"strategy-guide.md\""
        echo "       - backend/app/strategy/prompt_builder.py:10"
        echo "         _DOCS_DIR = Path(__file__).resolve().parent / \"prompts\""
    fi
else
    echo "     ⚠ patch 文件不存在: $PATCH_FILE"
fi

echo ""
echo "✅ 修复完成！请重新构建 Docker 镜像："
echo "   docker compose build --no-cache && docker compose up -d"
echo ""
echo "   或单独构建后端层（更快）："
echo "   docker compose build --no-cache app && docker compose up -d"
