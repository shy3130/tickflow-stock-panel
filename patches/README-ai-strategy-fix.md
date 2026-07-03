# AI 策略生成提示词文档缺失修复

## 问题

AI 策略生成总是生成结构不完整的策略代码，缺少 `basic_filter`、`scoring`、`ENTRY_SIGNALS`、`filter()` 等必要字段。

## 根因

两个问题叠加导致 Docker 容器中找不到运行时所需文档：

1. **`.dockerignore` 排除了 `docs/`**（第 37 行），这三个文件不进入 Docker 构建上下文：

   | 文件 | 作用 |
   |------|------|
   | `docs/strategy-guide.md` | LLM system prompt 的完整参考指南 |
   | `docs/strategy-builder-step1.md` | 步骤 1 提示词模板 |
   | `docs/strategy-builder-step2.md` | 步骤 2 提示词模板 |

2. **路径计算在 Docker 中不正确**：`Path(__file__).resolve().parent.parent.parent.parent` 在 Docker 中解析到 `/` 而非 `/app/`，导致代码找不到 `/docs/` 路径。

## 修复方法

将运行时依赖的 3 个 doc 文件放入 `backend/app/strategy/prompts/`，路径改为相对于当前文件的 `parent/prompts/`，这样：

- 文件随 `COPY backend/app ./app` 自动进入 Docker 镜像
- 路径在开发环境和 Docker 容器中解析一致
- 原始的 `docs/` 目录保留给人类读者，`prompts/` 只放运行时依赖

### 涉及文件

| 文件 | 修改 |
|------|------|
| `backend/app/strategy/prompts/` | **新建目录**，复制 `docs/` 中 3 个文件 |
| `backend/app/strategy/ai_generator.py:17` | `GUIDE_PATH` 改为 `Path(__file__).resolve().parent / "prompts" / "strategy-guide.md"` |
| `backend/app/strategy/prompt_builder.py:10` | `_DOCS_DIR` 改为 `Path(__file__).resolve().parent / "prompts"` |

### 验证方法

修复后重建 Docker 镜像，在容器内运行：

```bash
# 验证 guide 加载
docker exec TickFlow_Stock_Panel uv run python3 -c \
  "from app.strategy.ai_generator import AIStrategyGenerator; \
   print(len(AIStrategyGenerator()._get_guide()))"
# 输出: 10175

# 验证模板加载
docker exec TickFlow_Stock_Panel uv run python3 -c \
  "from app.strategy.prompt_builder import build_step1; \
   p=build_step1('T','D','long','R','ai_t'); \
   print('模板正确' if '步骤 1' in p else '模板缺失')"

# 验证端到端生成
docker exec TickFlow_Stock_Panel uv run python3 -c "
import asyncio
from app.strategy.ai_generator import AIStrategyGenerator
from app.strategy.prompt_builder import build_step1
async def t():
    r=await AIStrategyGenerator().generate(build_step1('S','D','long','R','ai_e2e'))
    print(f'valid={r[\"valid\"]} code_len={len(r[\"code\"])} has_meta={\"META\" in r[\"code\"]}')
asyncio.run(t())
"
```

## 拉取新版后重新应用

```bash
cd /opt/1panel/docker/compose/tickflow-stock-panel

# 方法一：使用脚本（推荐）
bash patches/apply-ai-strategy-fix.sh

# 方法二：手动操作
mkdir -p backend/app/strategy/prompts
cp docs/strategy-guide.md docs/strategy-builder-step1.md docs/strategy-builder-step2.md \
   backend/app/strategy/prompts/
# 然后手动修改两个 Python 文件的路径（见上方）

# 最后重建 Docker
docker compose build --no-cache && docker compose up -d
```
