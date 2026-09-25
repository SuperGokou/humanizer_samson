# 操作指南

## 安装与配置

在项目目录运行 `python3 -m pip install -r requirements.txt`。Python 3.10+，支持 macOS/Linux；语料 PDF 解析需安装 Poppler。改写模块本身不读取 PDF。

首次配置可从 `.env.example` 复制为 `.env`，填写 `DEEPSEEK_API_KEY`，然后 `chmod 600 .env`。已有 `.env` 不要覆盖。密钥仅由后端 Python 读取，环境变量优先；配置文件只解析赋值，不执行内容。只接受官方 DeepSeek HTTPS endpoint；不自动跟随重定向。

模型变量：Flash 默认评分、检索重排和初稿；Pro 复杂内容、失败修正和全文复核。`--model deepseek-v4-pro` 仅覆盖默认模型，便于对照实验。协议使用非思考模式 `thinking.type=disabled`、JSON object、4096 输出 token；截断输出不被接受。[官方接口说明](https://api-docs.deepseek.com/api/create-chat-completion/)。

## 先预检再调用

```bash
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-check --allow-candidates --glossary examples/glossary.json --dry-run
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-run --allow-candidates --glossary examples/glossary.json --max-calls 12
```

Science、Technology、Engineering、Mathematics、Finance 五个学科名称区分大小写。默认窗口 8 句、步长 4 句；`--window-size` 可取 5–10，`--stride` 必须大于 0 且小于窗口大小。短节可少于 5 句。标题、公式、代码、列表、表格、参考文献被保留；只对普通段落切句。规则切句对复杂缩写、混合语言和非标准 Markdown 仍需检查，HTML 对照页会显示实际对应关系。

术语表是 JSON 对象，例如 `{"standard error": [], "OLS": ["ordinary least squares"]}`；空列表表示仅允许原术语，别名列表表示可接受的替换。请避免重复或相互包含的别名，完整术语一致性还需人工复核。

`--dry-run` 无网络模型请求、不需要密钥；输出实际窗口和本地召回。默认只读取 ready 句库。当前 ready 为空，需先审核语料或显式 `--allow-candidates` 使用待质量复核的候选。候选状态和 DOI 会保留到报告，许可待核对/held 文献不会进入检索。没有同学科匹配时允许零参考，不虚构来源。`--no-retrieval` 是完全禁用参考的对照模式。

## 恢复和预算

```bash
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-run --allow-candidates --glossary examples/glossary.json --max-calls 12 --resume
```

`--max-calls` 限制本次实际 HTTP 尝试数，包括 429/5xx 重试；续跑有新的次数预算，报告累计所有次数和实际 token，不估算未配置的费用。不同文本、模型、提示词版本、术语、索引、窗口或模式不能共用检查点。目录非空时必须使用 `--resume`，否则换新目录。

成功模型回复先原子写入检查点，然后推进阶段；恢复时复用已完成阶段。认证、预算或服务暂时不可用造成 incomplete，可解决原因后续跑。请求超时或进程中断导致 in_flight 时，无法确认服务端是否完成/计费，标记 uncertain，禁止自动重发。可保留原目录作审计，确认愿意重新调用后，手动选新输出目录开始；不要随意编辑检查点。

状态与退出码：

| 状态 | 退出码 | 含义 |
| --- | --- | --- |
| dry_run | 0 | 仅本地预检 |
| complete | 0 | 流程和最终复核完成；不代表学术事实已获外部验证 |
| incomplete | 1 | 预算/服务/协议或复核未完成；输出应视为草稿 |
| uncertain | 1 | 服务端请求结果未知，未自动重复调用 |
| 参数或配置错误 | 2 | 输入、窗口、目录或语料不适用 |

数字、单位、引用、公式或术语变化会触发硬检查，普通窗口最多尝试一次 Pro 修正；仍失败保留该窗口负责的原句。复杂窗口直接使用 Pro，失败即回退。模型最终复核覆盖全文及章节/分片边界，发现问题先回退句子，再复核受影响段落与相邻句；仍失败保留整个原段落。规则不能证明所有语义等价，尤其数字与对象关系需人工检查。

## 输出与语料增量

- `rewritten.md`：保留原文结构的最终/当前草稿。
- `comparison.html`：原句与改句、编辑评分、参考段落及回退原因。所有论文/模型字符串均 HTML 转义。
- `report.json`：完整逐窗观察、评分中位数、来源、用量、请求参数、状态和限制。
- `checkpoint.json`：恢复缓存，包含模型回复和文章内容，不含密钥。
- `evaluation.csv`：原稿/改稿外部检测结果空表；续跑保留手工填写内容。

添加新资料放入 `corpus/inbox/`，然后运行：

```bash
python3 corpus/scripts/manage.py import corpus/inbox
python3 corpus/scripts/manage.py organize
python3 corpus/scripts/manage.py report
```

完整格式、审核和去重机制见 [语料指南](../corpus/README.md)。项目中的原始全文、解析产物、索引和 `runs/` 均默认保留本地。部署到新机器需导入语料并重新 organize；请妥善保存本机资料。
