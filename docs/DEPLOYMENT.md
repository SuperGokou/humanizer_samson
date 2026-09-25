# GitHub Pages Deployment

**Website:** [supergokou.github.io/humanizer_samson](https://supergokou.github.io/humanizer_samson/)

## What is deployed

The hosted site is a static English showcase of recorded synthetic Finance and Science runs. It includes the comparison page and sanitized JSON snapshots. It does not accept papers, call DeepSeek, or collect API keys.

| Setting | Value |
| --- | --- |
| Repository | `SuperGokou/humanizer_samson` |
| Repository visibility | Private |
| Website visibility | Public |
| Publishing source | `gh-pages`, root directory |
| Published content | `docs/demo/` only |
| HTTPS | Enforced |
| Build mode | GitHub Pages branch publishing |

The `.nojekyll` file serves the generated HTML directly. GitHub's Pages build and deployment run reports the deployment status.

## Update the site

From the project root, update the synthetic snapshots or the renderer and regenerate:

```bash
python3 scripts/build_demo.py
git add docs/demo scripts/build_demo.py
git commit -m "docs: update recorded demo"
git push origin HEAD:main
```

Publish only the demo directory:

```bash
publish_commit="$(git subtree split --prefix=docs/demo HEAD)"
git push origin "$publish_commit:refs/heads/gh-pages"
```

Normal updates preserve subtree history and do not require a force push. If the remote has diverged, inspect it before proceeding.

Verify the deployment:

```bash
gh api repos/SuperGokou/humanizer_samson/pages \
  --jq '{status, html_url, source, https_enforced}'
gh run list --repo SuperGokou/humanizer_samson --limit 5
```

Changes to `main` alone do not update the website; publish the demo subtree as shown above. Keep new website assets inside `docs/demo/` and use relative paths for local resources.

## Hosting the editor itself

GitHub Pages hosts static files; this project's Python pipeline requires a runtime with local corpus storage and server-side credentials. The deployed showcase therefore has no upload form or rewrite endpoint. Use the CLI for actual editing. A future hosted editor needs a separate backend, API-key protection, access control, and request limits; that backend is not included in this deployment.
