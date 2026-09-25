# Contextual Paper Rewriting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现可本地运行、可恢复、可审计的重叠窗口英文论文改写流程。

**Architecture:** 以原文字符位置和稳定句子 ID 为骨架，窗口共享上下文但各句仅有一个修改归属。BM25 召回与 Flash 重排提供风格参考，Flash 初稿经过硬校验，必要时升级 Pro，合并后由 Pro 标记风险并触发回退。模型调用、原文保护、语料审核状态和费用记录分别管理。

**Tech Stack:** Python 3.10+、requests、标准库 unittest / sqlite3 / html / json；沿用现有本地语料，不增加 embedding 服务。

**Spec:** `docs/superpowers/specs/2026-09-25-contextual-rewrite-design.md`（用户已确认）。

**Execution status:** 计划待审阅；以下勾选项目前均未执行。推荐 Native：在当前任务内逐项实现，完成后由独立审查者检查整体差异。

## Global Constraints

- 第一版输入 UTF-8 `.txt` / `.md`，提供命令行和清晰的本地使用说明。
- 窗口默认 8 句、步长 4 句；评分仍按句返回。
- 窗口大小可选 5–10，步长必须小于窗口大小。
- 每句在所有覆盖它的窗口中，归属距窗口中心最近的窗口；距离相等时取较早窗口。全文每句恰有一个归属窗口。
- 每个窗口可以评分全部覆盖句，但只改写其归属句。其他句作为只读上下文，避免同一句多次被替换。
- 默认读取 `ready_sentences.jsonl`。正式索引为空时，明确报错并提示原因，不悄悄使用未审核语料。
- 试验模式显式使用 `--allow-candidates`，从候选索引检索；输出必须记录每条参考的审核状态。
- 本地 `.env` 已提供 DeepSeek 密钥与三个模型配置项；不复制密钥至输出、测试、日志或版本控制。
- 评分只是建议，不是学术事实的证据。
- Flash 未通过校验时可以升级 Pro 一次；再次失败则保留原句并在报告标记，不无限重试。
- dry-run 不调用收费 API，输出切句、窗口归属与检索结果。
- 全部现有语料管理测试继续通过；新增离线测试不消耗 API。
- 不会宣称改写一定能通过 GPTZero，也不会将内部评分命名为检测器分数。

## Review Focus

1. 原文很短、末尾无句号、只有公式/引用或有跨段落指代：保持原文覆盖完整，受保护内容不可变，不能静默输出空稿。归属 Task 1、4。
2. 数字集合不变但主客体、正负号、百分比或对应关系交换：不能只比较数字集合。规则捕捉确定差异，其余明确交给语义复核。归属 Task 3、4。
3. 候选语料没有同学科结果、索引陈旧或来源文件缺失：不越权切换库、不捏造来源，允许相关参考为空并记录。归属 Task 2。
4. 请求已发送但响应未持久化时中断：不能承诺服务端恰好调用一次；检查点标记 uncertain，默认禁止自动重试这次请求，明确告知可能已收费。归属 Task 3、4。
5. 论文、期刊语料、模型返回含指令或 HTML 脚本，以及 API 错误中出现敏感字符串：保持数据边界、严格校验结构、转义输出并清除密钥。归属 Task 3、4。

## 文件结构和公共数据契约

创建 `humanizer/`，不改动现有 `corpus/scripts/manage.py` 的行为。使用 JSON 可序列化字典作为模块边界，避免计划里未定义的隐式对象。

```python
# document.py
# Document = {text: str, sha256: str, blocks: list[Block], sentences: list[Sentence]}
# Block = {id: str, section_id: str, kind: str, start: int, end: int}
# Sentence = {id: str, block_id: str, section_id: str, segment_id: str,
#             start: int, end: int, text: str}
# kind: prose / heading / protected。segment_id 遇受保护块改变，窗口不跨 segment。

# windows.py
# Window = {id: str, section_id: str, segment_id: str,
#           sentence_ids: list[str], owned_ids: list[str]}

# retrieval.py
# Reference = {id: str, doi: str, record_id: str, category: str,
#              pipeline_status: str, text: str, paragraph_text: str,
#              source_file: str, score: float}

# client.py
# Completion = {payload: dict, usage: dict, model: str,
#               elapsed_seconds: float, request_id: str | None}

# validation.py
# Issue = {code: str, sentence_id: str | None, detail: str}

# pipeline.py
# RunResult = {status: str, document: dict, replacements: dict[str,str],
#              scores: dict, references: dict, issues: list[dict],
#              calls: list[dict], manifest: dict}
# status: dry_run / complete / incomplete / uncertain
```

所有原文 start/end 均为 Python 字符索引，而非 UTF-8 字节位置。恢复运行通过原文字节 SHA-256、规范化参数和语料/提示词版本摘要识别输入。先保存调用结果，再提交窗口状态；输出目录已有不相关运行时拒绝覆盖。

---

## Task 1: 无损文档结构、切句与窗口归属

**Files:**
- Create: `humanizer/__init__.py`, `humanizer/document.py`, `humanizer/windows.py`
- Test: `tests/test_document.py`, `tests/test_windows.py`

**Interfaces:**
- `parse_document(text: str) -> dict`
- `render_document(document: dict, replacements: dict[str, str]) -> str`
- `make_windows(document: dict, size: int = 8, stride: int = 4) -> list[dict]`
- `aggregate_scores(results: list[dict]) -> dict`：相同句子、相同维度取中位数，保留 observations。

- [ ] **Step 1: 编写字符位置和窗口覆盖失败测试。** 测试类使用 unittest.TestCase；增加 1/4/8/9/12/17 句循环、Markdown 公式/代码块/参考文献、缩写、小数、无句号尾句以及不同章节不能混窗的测试。

```python
from humanizer.document import parse_document, render_document
from humanizer.windows import make_windows

def test_overlap_has_single_owner(self):
    text = ' '.join(f'Observation {i} is recorded.' for i in range(1, 13))
    doc = parse_document(text)
    windows = make_windows(doc)
    self.assertEqual([len(w['sentence_ids']) for w in windows], [8, 8])
    owners = [sid for w in windows for sid in w['owned_ids']]
    self.assertEqual(len(owners), 12)
    self.assertEqual(len(set(owners)), 12)
    self.assertEqual(render_document(doc, {}), text)

def test_preserves_nonprose_bytes(self):
    text = '# Results\n\nThe estimate is 3.14. Dr. Smith agrees.\n\n$$x=2$$\n\n```python\nx = 1\n```\n'
    doc = parse_document(text)
    self.assertEqual(len(doc['sentences']), 2)
    sid = doc['sentences'][0]['id']
    result = render_document(doc, {sid: 'The estimated value is 3.14.'})
    self.assertIn('$$x=2$$', result)
    self.assertIn('```python\nx = 1\n```', result)
```

- [ ] **Step 2: 运行测试并确认缺失功能导致失败。** `python3 -m unittest discover -s tests -p 'test_document.py' -v`，以及同样运行 `test_windows.py`。
- [ ] **Step 3: 实现保留分隔符的字符跨度解析。** 先识别 fenced code、display math、标题和参考文献区，再只对 prose 切句。括号/引号内末尾标点应与所属句一起保留；不按小数点切句。无法可靠识别的纯 Markdown 表格/列表保守作为 protected。

窗口生成停止条件及归属算法按以下实现，避免多生成已完整覆盖的尾窗：

```python
starts = []
start = 0
while start < len(segment_sentences):
    starts.append(start)
    if start + size >= len(segment_sentences):
        break
    start += stride

for index, sentence in enumerate(segment_sentences):
    covering = [w for w in local_windows if sentence['id'] in w['sentence_ids']]
    owner = min(covering, key=lambda w: (abs(index - centers[w['id']]), order[w['id']]))
    owner['owned_ids'].append(sentence['id'])
```

其中 centers 按窗口实际首尾句下标计算，order 为该 segment 内窗口序号；两个映射在创建 local_windows 时产生。render_document 按 start 倒序替换原文跨度，拒绝未知 ID，不重建原始空白和段落。

- [ ] **Step 4: 运行全套测试。** `python3 -m unittest discover -s tests -v`；新增评分汇总 20/80 两次观察得到 50 的断言，单次观察保持原分值。
- [ ] **Step 5: 提交。** `git add humanizer/__init__.py humanizer/document.py humanizer/windows.py tests/test_document.py tests/test_windows.py && git commit -m "feat: preserve document structure and build overlapping windows"`

## Task 2: 可追溯的本地风格检索

**Files:**
- Create: `humanizer/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- `StyleIndex(corpus_root: Path, allow_candidates: bool = False)`
- `StyleIndex.search(query: str, domain: str, limit: int = 20) -> list[dict]`
- `StyleIndex.fingerprint: str`：参与缓存的索引内容摘要。
- `select_references(candidates: list[dict], selected_ids: list[str], limit: int = 3) -> list[dict]`

- [ ] **Step 1: 使用隔离临时语料编写失败测试。** 每个 fixture 的 document.json 含两个不同段落；索引分别包含 Finance 与 Science、ready 与 held 记录。断言未启用候选时空正式库报错、Finance 不返回 Science、上下文从同 record_id/paragraph_id 获取、重排不能引用未知 ID。

```python
def test_candidate_access_is_explicit(self):
    with self.assertRaises(ValueError):
        StyleIndex(self.corpus_root)
    index = StyleIndex(self.corpus_root, allow_candidates=True)
    hits = index.search('bank liquidity risk', 'Finance')
    self.assertTrue(hits)
    self.assertTrue(all(h['category'] == 'Finance' for h in hits))
    self.assertTrue(all(h['pipeline_status'] == 'review_required' for h in hits))
    self.assertEqual(hits[0]['doi'], 'https://doi.org/10.1234/banking')
```

- [ ] **Step 2: 运行 `python3 -m unittest discover -s tests -p 'test_retrieval.py' -v`，确认失败。**
- [ ] **Step 3: 实现按学科构建的词项倒排索引与 BM25。** 仅纳入所选模式允许的状态；使用 Counter、posting lists、文档长度与词项频率，参数 k1=1.5、b=0.75。paragraph_text 从 processed 文档精确定位；来源损坏跳过并保存 diagnostics，不合成段落。

```python
idf = math.log(1 + (n_documents - document_frequency + 0.5) / (document_frequency + 0.5))
score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / mean_length))
```

不同论文以 DOI 或 record_id 去重，最多返回 3 篇。没有词项交集返回空结果。检索不能加载任意越出 corpus_root 的 source_file 或 processed_file 路径。

- [ ] **Step 4: 验证旧/新索引指纹不同、同 query 输出确定、缺源文件可诊断、恶意路径被拒绝。** 运行全部测试。
- [ ] **Step 5: 提交。** `git add humanizer/retrieval.py tests/test_retrieval.py && git commit -m "feat: retrieve traceable academic style references"`

## Task 3: API、严格响应协议和内容保护

**Files:**
- Create: `humanizer/config.py`, `humanizer/client.py`, `humanizer/validation.py`, `humanizer/prompts.py`
- Test: `tests/test_config.py`, `tests/test_client.py`, `tests/test_validation.py`

**Interfaces:**
- `load_config(project_root: Path, environ: dict | None = None, require_key: bool = True) -> dict`
- `DeepSeekClient(config: dict, max_calls: int, session=None, sleep=None)`
- `DeepSeekClient.complete(stage: str, model: str, payload: dict) -> dict`
- `DeepSeekClient.calls: list[dict]`，含每个尝试的状态和实际 usage。
- `validate_scores(payload: dict, expected_ids: list[str]) -> list[dict]`
- `validate_rewrites(payload: dict, expected_ids: list[str]) -> dict[str,str]`
- `check_invariants(original: str, rewritten: str, sentence_id: str, glossary: dict) -> list[dict]`
- `check_reference_overlap(text: str, references: list[dict], min_words: int = 12) -> list[dict]`
- `build_messages(stage: str, payload: dict) -> list[dict]`
- 明确定义异常：`ConfigurationError`, `ProtocolError`, `AuthenticationError`, `BudgetExceeded`, `TransientAPIError`。

- [ ] **Step 1: 编写响应、保护规则、密钥不泄露与调用预算失败测试。** 网络只替换 requests.Session 的传输边界；保留真实请求构造、JSON 校验、重试和用量逻辑。测试假响应包含 choices/message/content、finish_reason、usage，与实际接口形状一致。

```python
def test_missing_sentence_is_rejected(self):
    with self.assertRaises(ProtocolError):
        validate_rewrites({'rewrites': [{'id': 's1', 'text': 'A result.'}]}, ['s1', 's2'])

def test_numeric_changes_are_rejected(self):
    issues = check_invariants('Returns fell by -3.5% [12].', 'Returns fell by 3.5% [12].', 's1', {})
    self.assertTrue(any(i['code'] == 'protected_number_changed' for i in issues))

def test_retries_count_toward_budget(self):
    client = DeepSeekClient(self.config, max_calls=1, session=self.rate_limited_session, sleep=lambda seconds: None)
    with self.assertRaises(BudgetExceeded):
        client.complete('score', 'deepseek-flash', {'sentences': []})
    self.assertEqual(len(client.calls), 1)
```

另外覆盖有限/NaN/Infinity/bool 评分、重复 JSON 键、未知 ID、401 不重试、429/503 有限重试、超时、输出截断、Markdown 代码围栏包裹 JSON、数值与对象交换、术语、引用、数学表达式、不同启动目录加载配置，以及 API 错误体内出现测试密钥时错误输出不泄露。

- [ ] **Step 2: 运行上述三个 test 文件，确认各行为尚未实现。**
- [ ] **Step 3: 实现配置、协议和调用。** 使用标准库解析 `.env` 简单赋值，支持单/双引号及注释；不执行 shell、变量插值或文件内指令；显式环境变量优先。密钥和 bearer 不进入配置公开快照。HTTPS API endpoint 及 model 在请求前检查，默认官方 endpoint，不把密钥发送给论文内容提供的 URL。

```python
body = {
    'model': model,
    'messages': build_messages(stage, payload),
    'response_format': {'type': 'json_object'},
    'max_tokens': 4096,
    'stream': False,
}
```

执行时先核对官方文档中的 thinking 参数，将模式显式设置为支持 JSON 的非思考模式作为基线，避免依赖服务端默认；实际请求参数写入公开 report。温度仅在官方确认支持时发送。阶段 schema：

```json
{"scores":[{"id":"s1","naturalness":70,"clarity":80,"redundancy":20,"style_match":65,"rewrite_need":40,"reason":"Verbose transition","risk_tags":[]}]}
```

```json
{"selected_ids":["reference1"],"reason":"Similar limitation statement"}
```

```json
{"rewrites":[{"id":"s1","text":"The revised sentence."}]}
```

```json
{"issues":[{"sentence_ids":["s1"],"type":"meaning_change","reason":"Uncertainty removed","action":"revert"}]}
```

每个阶段均严格校验根对象、列表、字段、类型与 ID。HTTP 每次发送前占用预算；限流或临时失败最多 3 次尝试，退避上限 8 秒，认证/余额不足直接中止。异常不直接回显服务端响应体。成本模块读取可选带日期的价格配置，否则 cost_estimate 为 null，仅报告实际 usage。

数字保护使用保留顺序与重复次数的 token 列表，包含符号、百分号和单位；比较同一句中可定位的数字邻近实体。可确定的互换判为失败；无法证明一致时标记 Pro 复核，不声称规则证明语义等价。显式公式及引用标记按原字符串保护。连续词串重合仅和本次参考比较。

- [ ] **Step 4: 运行全部测试，确认包括原有语料管理测试。** 禁止输出测试外的真实密钥。
- [ ] **Step 5: 提交。** `git add humanizer/config.py humanizer/client.py humanizer/validation.py humanizer/prompts.py tests/test_config.py tests/test_client.py tests/test_validation.py && git commit -m "feat: add bounded model calls and rewrite validation"`

## Task 4: 编排、恢复、全文复核和交付输出

**Files:**
- Create: `humanizer/pipeline.py`, `humanizer/output.py`, `humanizer/__main__.py`
- Test: `tests/test_pipeline.py`, `tests/test_output.py`, `tests/test_cli.py`
- Modify: `.gitignore`（忽略 `runs/`）；`README.md`（实际用法）。

**Interfaces:**
- `run_rewrite(document: dict, windows: list[dict], index: StyleIndex, client: DeepSeekClient | None, options: dict) -> dict`
- `save_outputs(result: dict, output_dir: Path) -> None`
- `main(argv: list[str] | None = None) -> int`
- options 的必填键：domain, output_dir, dry_run, resume, models（default/complex/review）, glossary, allow_candidates, max_calls, input_sha256, prompt_version。显式 no_retrieval 只用于对照实验。

- [ ] **Step 1: 使用真实文档/检索/校验/输出和可控模型回复编写集成失败测试。** fake client 只返回确定的各阶段 payload；断言最终文件而非 mock 调用本身。

```python
def test_invalid_number_reverts_after_one_pro_attempt(self):
    result = run_rewrite(self.document, self.windows, self.index, self.always_changes_numbers_client, self.options)
    original = self.document['sentences'][0]
    self.assertEqual(result['replacements'].get(original['id'], original['text']), original['text'])
    self.assertTrue(any(i['code'] == 'reverted_after_validation' for i in result['issues']))

def test_output_escapes_article_html(self):
    self.result['document']['text'] = '<script>alert(1)</script>'
    save_outputs(self.result, self.output_dir)
    html = (self.output_dir / 'comparison.html').read_text()
    self.assertNotIn('<script>alert(1)</script>', html)
    self.assertIn('&lt;script&gt;', html)
```

增加中途预算耗尽后恢复成功且已经完成窗口不变、输入或参考指纹改变拒绝 resume、uncertain 状态不重发、错误窗口 ID、重叠评分中位数、只保护块的输入、多个章节边界复核和最终回退仍有衔接问题时整段回退的用例。

- [ ] **Step 2: 运行 test_pipeline.py / test_output.py / test_cli.py，确认失败。**
- [ ] **Step 3: 实现固定执行顺序与检查点。** 每窗按照 retrieve → rerank → score → rewrite → invariants → optional Pro correction 保存阶段结果。共享上下文用原文；只向归属句写 replacement。重排未知 ID 是协议错误。无可用参考无需调用重排；如无需修改，可返回原句并记录原因。

```python
manifest = {
    'input_sha256': options['input_sha256'],
    'models': options['models'],
    'prompt_version': options['prompt_version'],
    'index_fingerprint': index.fingerprint,
    'glossary': options['glossary'],
    'window_size': options['window_size'],
    'stride': options['stride'],
    'domain': options['domain'],
    'allow_candidates': options['allow_candidates'],
}
cache_key = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
```

调用前以原子写入记录 in_flight，结果成功落盘后置 completed。进程中断后遗留 in_flight 视为 uncertain，默认停止并说明可存在已计费请求；不声称本地缓存能够恢复服务端未返回的响应。dry-run 在 client 为 None 时完整走窗口与本地召回并输出报告。

完成窗口后按原始字符跨度合并；Pro 检查跨句、否定、因果、程度和指代，返回涉及的句子 ID。问题句回退后复查所属段落；仍不通过则该原段落整体回退。长章节按字符预算分片并有边界窗口，预算不足时标为 incomplete，不把缺少最终复核的结果标为 complete。不存在静默文本截断。

输出 rewritten.md、comparison.html、report.json、checkpoint.json 和 evaluation.csv。报告包含完整观察与来源状态；HTML 所有论文、来源、理由字符串使用 html.escape；外链仅允许 https://doi.org/ 形式。评价 CSV 的 detector_score 默认留空。

- [ ] **Step 4: 实现 CLI 和实际用法。** 在 API 前完成参数、文件编码、索引可用性与输出目录检查。`.env` 从包所在项目目录找；dry-run 不要求密钥。窗口参数非法退出码 2；受控 incomplete/uncertain 退出码 1；完整成功或 dry-run 返回 0。

```bash
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-dry --allow-candidates --dry-run
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-live --allow-candidates --max-calls 12
python3 -m humanizer rewrite examples/finance_synthetic.md --domain Finance --output runs/finance-live --allow-candidates --max-calls 12 --resume
```

resume 的 max-calls 是本次继续执行可用调用数，报告同时保存累计调用量；输入、模型、检索与保护规则等策略必须一致。输出已存在且未指定 resume 时拒绝覆盖。

- [ ] **Step 5: 全套测试并提交。** `python3 -m unittest discover -s tests -v`；`git add humanizer/pipeline.py humanizer/output.py humanizer/__main__.py tests/test_pipeline.py tests/test_output.py tests/test_cli.py .gitignore README.md && git commit -m "feat: orchestrate contextual rewriting with resumable reports"`

## Task 5: 真实语料验证、合成样本联网验收与文档

**Files:**
- Create: `examples/finance_synthetic.md`, `examples/science_synthetic.md`, `examples/glossary.json`
- Create: `docs/USAGE.md`, `docs/EVALUATION.md`
- Create at runtime, ignored by Git: `runs/finance-live/`, `runs/science-live/`, `runs/verification.json`
- Modify: `README.md`（完成状态与局限）。

**Interfaces:** 消费 Task 4 CLI 和输出，不引入新模型行为。公开 examples 的首行明确说明“合成流程测试文本，不是真实研究”。

- [ ] **Step 1: 编写八句 Finance 样本及八句 Science 样本。** 内容采用虚构实验数字、明确的相关性限定、一个术语和一个占位引用，以测试保持原意；不写成真实研究发现。例如：

```text
Synthetic workflow fixture; not a real research result.

# Results
In this synthetic example, the sample contains 120 observations. The estimated coefficient is 0.15. The standard error is 0.04. These quantities are illustrative rather than empirical findings. The association does not establish causation. Unobserved differences may affect the estimate. The interpretation follows the predefined terminology [1]. Further validation would be needed before any substantive conclusion.

# References
[1] Synthetic placeholder for pipeline testing; not a published source.
```

Science 样本使用同样八句结构，包含 25 °C、10 mL、0.20 与相关性限定，不借用真实论文结果。glossary.json 为术语到允许表达列表的 JSON，例如 `{"standard error": ["standard error"]}`。

- [ ] **Step 2: 完整运行离线测试及两个 dry-run。** 将命令、退出码、测试数与语料指纹保存至 verification.json。另确认未显式启用候选时当前空正式库会按预期报错。
- [ ] **Step 3: 核对官方 DeepSeek API 参数后，分别运行最多 12 次调用的联网样本。** 使用真实 `.env`，不发送用户私有论文。记录真实模型、token、耗时、是否升级、回退与最终状态；如果费用价格配置未核实，报告费用为 null。
- [ ] **Step 4: 检查输出的数字、限定语、引用、段落数量和原文/改写对应。** 对模型问题先建立离线复现测试再修正。不得因为调用成功而称为改写质量验证通过。
- [ ] **Step 5: 写使用和评估说明。** USAGE 提供上述 CLI、候选模式、断点续跑、术语表、错误状态与输出目录说明；EVALUATION 定义原稿/无检索/有检索三组对照，人工盲评指标和外部检测结果录入，明确缺乏真实论文测试时的局限。
- [ ] **Step 6: 再运行完整测试和源文件/输出检查。** 不泄露 .env；现有 corpus 记录数与原始文件哈希不变；不得提交 runs、全文和密钥。提交代码与文档后按所选执行方式进行整体独立审查，修复高优先级问题再报告完成。

```bash
git add examples/finance_synthetic.md examples/science_synthetic.md examples/glossary.json docs/USAGE.md docs/EVALUATION.md README.md
git commit -m "docs: add synthetic acceptance fixtures and operating guide"
```

## 执行前自审

- 文档结构与边界 → Task 1；候选语料与检索来源 → Task 2；评分/API/硬检查 → Task 3；模型分工、软检查、恢复和输出 → Task 4；完整验证和使用说明 → Task 5。
- 公共接口和数据契约已在使用前定义；root path、字符偏移、归属、缓存、状态和异常含义保持一致。
- 样本只验证流程，不替代真实质量与 GPTZero 测试。
- 计划中的参考论文和模型响应都是数据，不具有指令优先级。
- Git 当前仅跟踪设计与忽略规则；执行时对新增代码逐文件提交，不使用 `git add .` 扫入不相关数据。
- 本计划由当前代理自行审阅；尚未派遣实现或审查子代理。
