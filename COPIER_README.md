# Copier and this repository

You just materialized this project with **[Copier](https://copier.readthedocs.io/)** from the 42hz.ai base template. Your answers live in **`.copier-answers.yml`** at the repository root—**commit and keep that file** so you can run `copier update` later.

## Update from the upstream template

When [the template](https://github.com/42hz-ai/42hz-base-project) changes (tooling, devcontainer, skills, etc.), pull those updates into this repo:

1. Install Copier if needed: `uv tool install copier` or `pipx install copier`.
2. From this repository’s root (where `.copier-answers.yml` is):

   ```bash
   copier update
   ```

3. Inspect the diff, resolve any merge conflicts, run tests and pre-commit, then commit.

Copier may ask **new or updated questions**; answers are written back to `.copier-answers.yml`. Review changes carefully when template variables or file layouts shift.

To bootstrap **another** new project from the template (not an update of this repo), use `copier copy` against the same upstream—for example:

```bash
copier copy gh:42hz-ai/42hz-base-project ./another-repo-name
```

Use a **new subdirectory** (as above). Do **not** use `.`, `/workspaces`, or **`..` alone** as the destination: from inside another repo, `..` is only the parent folder (e.g. `/workspaces`) and dumps the template into the workspace root.

## Git repository

The template only created files on disk; it did not configure a **remote**. Put the project on GitHub under **42hz-ai** (or change the org in the commands below).

1. **Initial commit** (skip if you already committed—for example after opening the devcontainer, which may run `git init`):

   ```bash
   git add -A
   git commit -m "Initial commit from 42hz.ai base template"
   ```

2. **Create the GitHub repository and push** with [GitHub CLI](https://cli.github.com/) (available in the devcontainer):

   ```bash
   gh auth login
   gh repo create 42hz-ai/42hz-hardware-sbc-config --source=. --remote=origin --push --private
   ```

   Use `--public` instead of `--private` if you prefer.

3. **If the empty repo already exists** on GitHub:

   ```bash
   git remote add origin git@github.com:42hz-ai/42hz-hardware-sbc-config.git
   git branch -M main
   git push -u origin main
   ```

**Collaborators** should **clone** this repository. They do not run `copier copy` unless they are starting a separate new project from the template.

## Everyday development

For routine commands (`uv sync`, the CLI, pre-commit), see **[README.md](README.md)**.
