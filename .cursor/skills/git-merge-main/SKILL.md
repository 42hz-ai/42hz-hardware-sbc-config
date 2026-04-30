---
name: git-merge-main
description: Merge feature branches back into main branch. Use when merging feature branches, completing features, or when the user asks to merge changes back to main.
---

# Git Merge to Main

Merge feature branches back into main branch.

## Workflow

### 1. Switch to main branch

```bash
git checkout main
```

### 2. Pull latest changes (if remote exists)

```bash
git pull origin main
```

If no remote is configured, continue without pulling.

### 3. Merge the feature branch

```bash
git merge feat/branch-name
```

Replace `feat/branch-name` with the actual feature branch name.

### 4. Delete the merged branch (optional)

After successful merge, delete the feature branch:

```bash
git branch -d feat/branch-name
```

Use `-D` instead of `-d` if the branch hasn't been fully merged (force delete).

### 5. Verify merge

```bash
git log --oneline -3
git status
```

## Complete Example

**User**: "Merge feat/sqlite-commands back to main"

**Agent**:

1. Switch to main: `git checkout main`
2. Pull latest: `git pull origin main` (or skip if no remote)
3. Merge branch: `git merge feat/sqlite-commands`
4. Delete branch: `git branch -d feat/sqlite-commands`
5. Verify: `git log --oneline -3`

## Merge Types

- **Fast-forward merge**: No merge commit needed, clean history
- **Merge commit**: Creates a merge commit when branches diverged

Both are acceptable. Prefer fast-forward when possible.

## Notes

- Always merge from main (not into feature branch)
- Verify working tree is clean before merging
- If merge conflicts occur, resolve them before completing the merge
- Delete feature branches after successful merge to keep repository clean
