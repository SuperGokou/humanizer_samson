# Humanizer EN · Recorded Demo

[Live Demo](https://supergokou.github.io/humanizer_samson/) · [Project overview](../../README.md) · [Offline HTML preview](index.html)

> These are recorded API results for synthetic workflow fixtures—not real research, a live editor, or a detector benchmark. No API key is needed to view them.

## At a glance

| Fixture | Sentences | Final changes | API requests | Total tokens | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| Finance | 8 | 2 | 4 | 16,702 | complete |
| Science | 8 | 0 | 5 | 17,508 | complete |

The runs below use prompt `contextual-2`. Current code uses `contextual-3`, with subsequent context/provenance fixes verified offline. Token counts are recorded usage; monetary cost and external detector scores were not measured.

## Finance

[Original fixture](../../examples/finance_synthetic.md) · [Synthetic result snapshot](data/finance.json)

| Sentence | Original | Final revision |
| --- | --- | --- |
| 01 · Retained | In this synthetic example, the sample contains 120 observations. | In this synthetic example, the sample contains 120 observations. |
| 02 · Revised | It is important to note that the estimated coefficient is 0.15. | The estimated coefficient is 0.15. |
| 03 · Retained | The standard error is 0.04. | The standard error is 0.04. |
| 04 · Retained | These quantities are illustrative rather than empirical findings. | These quantities are illustrative rather than empirical findings. |
| 05 · Revised | Furthermore, the association does not establish causation. | Moreover, the association does not establish causation. |
| 06 · Retained | Unobserved differences may affect the estimate. | Unobserved differences may affect the estimate. |
| 07 · Retained | The interpretation follows the predefined terminology [1]. | The interpretation follows the predefined terminology [1]. |
| 08 · Retained | Further validation would be needed before any substantive conclusion. | Further validation would be needed before any substantive conclusion. |

All numbers, the placeholder citation [1], and the non-causal qualification remain in the final output.
The recorded validation and final-review stages raised no issues. This is not a guarantee of semantic equivalence.

### Traceable style references

| DOI | Source status |
| --- | --- |
| [10.1007/s10901-017-9551-8 ](https://doi.org/10.1007/s10901-017-9551-8) | `review_required` |
| [10.1007/s10640-021-00585-7 ](https://doi.org/10.1007/s10640-021-00585-7) | `review_required` |
| [10.1371/journal.pone.0176546 ](https://doi.org/10.1371/journal.pone.0176546) | `review_required` |

References supplied stylistic context only; their scientific claims are not evidence for these synthetic fixtures. Full third-party paragraphs are omitted from the distributable demo.

### Recorded model calls

| Stage | Model |
| --- | --- |
| rerank | `deepseek-flash` |
| score | `deepseek-flash` |
| rewrite | `deepseek-flash` |
| review | `deepseek-v4-pro` |
## Science

[Original fixture](../../examples/science_synthetic.md) · [Synthetic result snapshot](data/science.json)

| Sentence | Original | Final revision |
| --- | --- | --- |
| 01 · Retained | In this synthetic example, the sample was maintained at 25 °C. | In this synthetic example, the sample was maintained at 25 °C. |
| 02 · Retained | It is important to note that the solution volume was 10 mL. | It is important to note that the solution volume was 10 mL. |
| 03 · Retained | The response ratio was 0.20. | The response ratio was 0.20. |
| 04 · Retained | These quantities are illustrative rather than experimental findings. | These quantities are illustrative rather than experimental findings. |
| 05 · Retained | Furthermore, the association does not establish causation. | Furthermore, the association does not establish causation. |
| 06 · Retained | Uncontrolled variation may affect the response ratio. | Uncontrolled variation may affect the response ratio. |
| 07 · Retained | The interpretation follows the predefined protocol [1]. | The interpretation follows the predefined protocol [1]. |
| 08 · Retained | Further validation would be needed before any substantive conclusion. | Further validation would be needed before any substantive conclusion. |

All numbers, the placeholder citation [1], and the non-causal qualification remain in the final output.
The review stage requested a reversion. Its recorded reason was “Uncertainty removed”. This is a model judgment, not an independently established defect; the final output conservatively retains the original.

### Traceable style references

| DOI | Source status |
| --- | --- |
| [10.1038/s41467-019-09234-6 ](https://doi.org/10.1038/s41467-019-09234-6) | `review_required` |
| [10.1107/s090744490804362x ](https://doi.org/10.1107/s090744490804362x) | `review_required` |
| [10.1186/gb-2010-11-10-r106 ](https://doi.org/10.1186/gb-2010-11-10-r106) | `review_required` |

References supplied stylistic context only; their scientific claims are not evidence for these synthetic fixtures. Full third-party paragraphs are omitted from the distributable demo.

### Recorded model calls

| Stage | Model |
| --- | --- |
| rerank | `deepseek-flash` |
| score | `deepseek-flash` |
| rewrite | `deepseek-flash` |
| review | `deepseek-v4-pro` |
| review | `deepseek-v4-pro` |

## Run your own example

From a fresh checkout, try a free, local preflight:

```bash
python3 -m humanizer rewrite examples/finance_synthetic.md \
  --domain Finance --output runs/demo-dry --no-retrieval --dry-run
```

For model-backed editing, configure `.env` and follow the [quick start](../../README.md#quick-start). The development corpus is not bundled with the repository.

## Open the browser preview

Open the [hosted GitHub Pages demo](https://supergokou.github.io/humanizer_samson/), or download the repository and open `docs/demo/index.html` directly in a browser. GitHub renders this Markdown page but displays HTML files as source. The browser preview is static and works offline; it has no upload form or live model connection.

Regenerate the demo after updating its synthetic snapshots:

```bash
python3 scripts/build_demo.py
```
