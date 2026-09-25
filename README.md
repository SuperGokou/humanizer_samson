# Humanizer EN — 上下文感知学术英文改写

保留原文结构，按默认 8 句、步长 4 句的重叠窗口分析，用同学科历史期刊提供可追溯的文风参考。Flash 负责逐句评分与初稿，Pro 处理复杂窗口、失败修正和最终复核。每句只有一个改写窗口，保留数字、引用、公式及术语；验证失败会回退原文。

支持 UTF-8 `.txt` / `.md`，macOS / Linux，Python 3.10+。未提供 DOCX/PDF 输入编辑、网页界面或检测器自动提交。模型评分是编辑判断，不是 AI 检测概率，也不保证通过 GPTZero。

```bash
python3 -m pip install -r requirements.txt
# 不调用 API：检查切句、窗口和本地检索
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-dry --allow-candidates --dry-run
# 实际改写（最多 12 次请求，包括重试）
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-live --allow-candidates --max-calls 12
# 继续预算不足等可恢复任务，本次最多再调用 12 次
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-live --allow-candidates --max-calls 12 --resume
```

输出：`rewritten.md`、安全转义的 `comparison.html`、完整来源/逐句评分/回退/用量 `report.json`、`checkpoint.json`、留空供真实检测结果填写的 `evaluation.csv`。`runs/` 默认不进入 Git；模型回复可能含原文，运行目录应作为论文数据保管。

## 配置与语料

密钥只放项目根目录 `.env`，参考 `.env.example`。读取位置相对项目，不依赖启动目录；环境变量可覆盖文件配置。`.env` 和备份已忽略。

- `DEEPSEEK_MODEL=deepseek-flash`
- `DEEPSEEK_COMPLEX_MODEL=deepseek-v4-pro`
- `DEEPSEEK_REVIEW_MODEL=deepseek-v4-pro`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`

已有 5 学科各 200 条文献记录。正式审核通过的句库当前为空；候选库有 78,370 句，来自 299 篇需质量复核的文献。默认拒绝使用候选；实验命令通过 `--allow-candidates` 显式启用。其他许可待核对文献不会用于改写。原始全文、解析产物和索引保存在本地；新安装需自行导入/下载并整理语料。

```bash
python3 corpus/scripts/manage.py import corpus/inbox
python3 corpus/scripts/manage.py organize
python3 -m unittest discover -s tests -v
```

PDF 语料提取依赖 Poppler 的 `pdftotext`。增量维护命令支持 DOI、JSON、CSV、PDF/XML/TXT，详见 [语料维护指南](corpus/README.md) 和 [语料状态](corpus/reports/STATUS.md)。

实施方案见 [设计文档](docs/superpowers/specs/2026-09-25-contextual-rewrite-design.md) 和 [执行计划](docs/superpowers/plans/2026-09-25-contextual-rewrite.md)。
