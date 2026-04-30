---
name: doc-create
description: Creates and names prefixed, numbered docs under docs/ following the {REPO_ID}-{PREFIX}-{NNNN}-{kebab-slug}.md convention. Supports INFRA (infrastructure, CDK, cloud) and CODE (ADRs, developer guides, technical decisions) series. Use when adding a new doc, finding the next doc number, checking naming conventions, or when the user mentions doc-create, INFRA-, CODE-, or numbered documentation.
---

# Doc Create

All docs in this repo use a single filename format — within the repo and in any central archive:

**`{REPO_ID}-{PREFIX}-{NNNN}-{kebab-slug}.md`**

This repo's `REPO_ID` and active prefixes are in `.cursor/rules/doc-create.mdc`.

## Filename components

| Part         | Format                           | Example               |
| ------------ | -------------------------------- | --------------------- |
| `REPO_ID`    | 4–5 uppercase alphanumeric chars | `IDCTR`               |
| `PREFIX`     | Uppercase series identifier      | `INFRA`, `CODE`       |
| `NNNN`       | Zero-padded 4-digit integer      | `0001`, `0042`        |
| `kebab-slug` | Short lowercase kebab title      | `aws-identity-center` |

## Prefixes

| Prefix  | Covers                                                                         |
| ------- | ------------------------------------------------------------------------------ |
| `INFRA` | Infrastructure, cloud platform, CDK, AWS, deployments                          |
| `CODE`  | Architecture decisions (ADRs), developer guides, onboarding, technical how-tos |

## Next number

```bash
ls docs/ | grep "^{REPO_ID}-{PREFIX}-" | sort | tail -1
```

Take the `NNNN` from that filename and add 1. First doc in a series starts at `0001`.

## After adding a doc

1. Add a row to `docs/README.md` (the table of contents).
2. Link from the relevant hub doc or related parent doc.
3. Do not leave orphan docs unlinked from `docs/README.md`.

## Checklist

- [ ] Filename follows `{REPO_ID}-{PREFIX}-{NNNN}-{kebab-slug}.md`
- [ ] NNNN is zero-padded and one higher than the current highest in that series
- [ ] `docs/README.md` row added
- [ ] Linked from hub doc or related parent doc
