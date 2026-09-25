# 语料库：整理与增量添加

本地路径：`/Users/mingxia/Desktop/Humanizer_EN/corpus`。

[当前统计](reports/STATUS.md) · [总清单](catalog.csv) · [初始采集说明](snapshots/initial/README.md)

已收集的 1000 条记录是初始批次，不是容量限制。后续添加不会重新抽样或删除已有论文。年份默认截至 2021 年，语言默认英文，规则在 `config.json`。不符合或信息不完整的记录仍可保存，但不会进入可用句子索引。

## 最常用的添加方法

把新 PDF、XML、CSV/JSON 题录或 DOI 文本放入 `inbox/`，在项目目录执行：

```bash
cd /Users/mingxia/Desktop/Humanizer_EN
python3 corpus/scripts/manage.py import corpus/inbox
python3 corpus/scripts/manage.py organize
```

第二次执行相同导入不会新增重复记录；整理只重新处理原件变更、解析器版本变更或尚未处理的文件。原始输入保留在 inbox，可自行移走归档。

### 添加 PDF / XML

JATS XML 自动读取 DOI、标题、年份、期刊和许可声明。PDF 请同时提供同名 JSON，例如 `paper.pdf` 与 `paper.json`，内容参照 `templates/paper.json.example`。模板中的 DOI 是占位符，必须替换。

没有 DOI 的文件也能按 SHA-256 登记，但在补齐元数据和核验身份前不会作为可用风格样本。单次导入可以指定缺失的分类：

```bash
python3 corpus/scripts/manage.py import corpus/inbox --category Finance
```

分类可选 Science、Technology、Engineering、Mathematics、Finance。默认只填补缺失分类，不替换已有分类。

### 添加题录

CSV 模板为 `templates/papers.csv`；JSON 可以是对象或对象数组。至少提供 DOI，或随附可定位的文件。CSV 的 `local_file` 相对该 CSV 所在目录解析；原件会复制到内容哈希命名的路径。

JSON/CSV 导入以用户提供的元数据为输入，不自动声明其许可或论文质量已经核实。已有标题、年份、分类等非空字段不会被自动覆盖；人工修正应审慎修改主清单，先保留快照，不要修改导出的 CSV 期待自动生效。

### 添加 DOI 列表

`templates/dois.txt` 展示格式，每行一个 DOI。联网导入会从 OpenAlex 补充题录；接口失败时仍登记 DOI 并保留错误，稍后可补齐。

```bash
python3 corpus/scripts/manage.py import corpus/inbox/dois.txt --category Finance
# 仅登记 DOI，不访问网络
python3 corpus/scripts/manage.py import corpus/inbox/dois.txt --category Finance --offline
# 为已有、尚无全文的记录尝试获取开放全文，每次最多 20 篇
python3 corpus/scripts/manage.py fetch --limit 20
python3 corpus/scripts/manage.py organize
```

`fetch` 每次重新尝试没有全文的记录，保留失败原因；已下载原件和人工复核不被覆盖。每次按清单顺序取前 N 个待获取项，遇到持续失败的条目可以补充本地文件或增大 limit；没有偷偷跳过失败或循环下载成功文件。它只尝试开放全文来源，不绕过网站限制。

## 整理结果

- `catalog.json`：唯一主清单，包含稳定 record_id、DOI、下载状态、人工复核、处理状态和来源；新增导入记录保留 import_sources 原始输入路径。
- `catalog.csv`、五类 CSV、`references.bib`、`reading_lists/`：派生输出，每次自动更新。
- `fulltext/`：原始 XML/PDF，不因清洗被改写；新增文件按哈希保存。新版本保留旧版本路径；批准记录绑定原件哈希，替换全文后必须重新复核。
- `processed/<record_id>/document.json`：段落、句子、章节、XML XPath / PDF 页码和公式源 XML。
- `processed/<record_id>/body.txt`：供浏览的正文。XML 公式以 `[FORMULA_n]` 保留位置，原始公式存在 document.json 中。
- `index/candidate_sentences.jsonl`：许可和基本条件满足、仍待人工质量复核的句子，加上已批准的句子。不是经过最终审核的知识库。
- `index/ready_sentences.jsonl`：明确批准且满足全部检查条件的句子。
- `reports/review_queue.json`：需要补全文、补元数据、核验许可/身份、OCR 或质量复核的记录。
- `reports/possible_duplicates.json`：标题相同但未按 DOI/文件哈希合并的候选，留待复核。
- `reports/unreferenced_files.json`：未被当前记录或其他格式附件引用的文件；不会自动删除。
- `snapshots/`、`history.jsonl`：每次实际修改前的主清单备份、变更摘要和历史。无变化导入不增加历史。

XML 清洗排除参考文献、图表中的段落，保留正文与公式；PDF 使用保守的重复页眉页脚和参考文献边界清理，公式、多栏和断行仍需复核。切句是规则初版，保留段落关系，未声称达到人工标注质量。

## 状态与复核

| 状态 | 含义 |
|---|---|
| metadata_only | 只有题录，待补全文 |
| processing_pending | 已有原件，尚未解析 |
| processing_error / integrity_error | 解析失败或原件哈希不匹配 |
| license_review | 许可未知、限制或冲突 |
| metadata_review / identity_review | 关键信息缺失或全文身份尚未核验 |
| out_of_scope / retracted | 超出年份/语言范围，或撤稿 |
| review_required | 基本检查通过，等待学科、文章类型与表达质量复核 |
| held | 人工暂停或排除 |
| ready | 人工批准且通过检查，可进入正式句子索引 |

人工完成文章类型、相关性和文本质量核查后，可以登记结论：

```bash
python3 corpus/scripts/manage.py review '10.xxxx/真实DOI' --decision approve --note '已检查论文类型、主题和正文质量'
python3 corpus/scripts/manage.py review '10.xxxx/真实DOI' --decision hold --note '暂不使用，待核对'
```

也可以用 record_id 定位无 DOI 记录。approve 不会绕过许可、年份、身份或解析失败检查。许可不明需补充真实许可证据；不能只把状态改成 ready。

## 更新、重试和恢复

```bash
# 原件修复或补齐后重跑；成功条目会跳过
python3 corpus/scripts/manage.py organize
# 只重建派生报表，不改写本说明
python3 corpus/scripts/manage.py report
```

导入在提交主清单前完成校验，遇到 DOI 冲突或非法 DOI 整批不提交。原子替换避免留下半个 JSON；同一目录的修改通过文件锁串行化。如果进程在复制原件后、提交清单前中断，可能留下未引用文件，审计报表会列出；重跑导入可复用这些文件。

恢复时先停止运行中的管理命令，保留当前 `catalog.json`，从 `snapshots/<时间>/catalog.json` 恢复相应版本，再执行 `report`。快照恢复的是题录和状态，不删除新增原件，也不回退已经下载的原件；原件按哈希和版本路径保留。`snapshots/initial/` 保存本次机制上线前的原始主清单和说明。

旧的 collect.py / download.py / report.py 已改为增量入口；原有一次性脚本存为 `scripts/legacy/*.py.txt`，避免误运行覆盖语料。日常统一使用 manage.py。

## 验证

在项目目录执行 `python3 -m unittest discover -s tests -v`。测试使用隔离临时目录，不修改真实语料，不依赖外网。
