---
name: git-commit-code
description: Fix common pre-commit hook issues before committing code. Use when preparing to commit, when pre-commit hooks fail, or when the user asks to fix linting, formatting, or import sorting issues.
---

# Commit Code

Fix common pre-commit hook issues before committing.

## Quick Fix Workflow

Run these commands in order before committing:

```bash
# 1. Fix linting issues (unused imports, etc.)
uv run ruff check --fix .

# 2. Format code
uv run ruff format .

# 3. Sort imports
uv run ruff check --select I --fix .
```

## Common Issues and Fixes

### Import Sorting (I001)

**Error**: "Import block is un-sorted or un-formatted"

**Fix**:

```bash
uv run ruff check --select I --fix <file-or-directory>
```

### Unused Imports (F401)

**Error**: "imported but unused"

**Fix**:

```bash
uv run ruff check --fix <file-or-directory>
```

### Code Formatting

**Error**: ruff-format failures

**Fix**:

```bash
uv run ruff format <file-or-directory>
```

### Line Endings and Whitespace

These are auto-fixed by pre-commit hooks, but you can manually fix:

```bash
# Fix trailing whitespace and line endings
pre-commit run trailing-whitespace --all-files
pre-commit run mixed-line-ending --all-files
pre-commit run end-of-file-fixer --all-files
```

## Before Committing Checklist

Run this sequence before `git commit`:

```bash
# Fix all Python issues
uv run ruff check --fix .
uv run ruff format .
uv run ruff check --select I --fix .

# Review changes and ask user what to commit
git status
# Ask user: "What files should be committed?"

# Stage only what user wants
git add <specific-files>

# Verify staged changes
git diff --cached

# Then commit (with user-provided message)
git commit -m "your message"
```

**Remember**: Always ask the user what they want to commit. Don't automatically stage everything.

## Complete Commit Workflow

When committing code, follow these steps:

### 1. Fix pre-commit issues

```bash
uv run ruff check --fix .
uv run ruff format .
uv run ruff check --select I --fix .
```

### 2. Review changes and ask user what to commit

**IMPORTANT**: Always show the user what changes exist and ask what they want to commit. Never automatically commit all changes.

```bash
# Show current status
git status

# Show what files have changed
git status --short

# Show diffs for modified files
git diff
```

**Ask the user**: "What files would you like to commit?" or "Should I commit all these changes?"

Wait for user confirmation before proceeding.

### 3. Stage only what the user wants

Based on user's response, stage specific files:

```bash
# Stage specific files
git add path/to/file1.py path/to/file2.py

# Or if user confirms all changes
git add -A
```

**Note**: Use `git add -A` only if the user explicitly confirms. Otherwise, stage specific files.

### 4. Verify what will be committed

```bash
git status
git diff --cached    # Review staged changes
```

**Show the user** what's staged and confirm before committing.

### 5. Commit with message

**Ask the user** for a commit message, or suggest one based on the changes:

```bash
git commit -m "Descriptive commit message"
```

### 6. Verify commit succeeded

```bash
git log --oneline -1
git status
```

## Commit Message Guidelines

Write clear, descriptive commit messages that explain **what** changed and **why** (when relevant).

### Format Structure

**First line (subject):**

- Start with a verb in imperative mood
- Length: 50-72 characters
- Capitalize first letter
- No period at the end
- Describe what the commit does

**Body (optional, for complex changes):**

- Blank line after subject
- Explain **why** the change was made (if not obvious)
- Explain **how** if the approach is non-obvious
- Wrap at 72 characters
- Use bullet points for multiple changes

**Footer (optional):**

- Reference issues: `Fixes #123` or `Closes #456`
- Breaking changes: `BREAKING CHANGE: description`

### Good Examples

**Simple, clear:**

```
Add SQLite command group with init and query commands
```

**With body explaining context:**

```
Refactor SQLite modules to use sqlite-utils library

Replace raw sqlite3.Connection usage with sqlite_utils.Database
throughout all SQLite modules. This provides a cleaner API,
better type hints, and access to sqlite-utils features like
transforms and full-text search.

- Update DatabaseManager to use sqlite-utils Database
- Refactor init, query, create_table, and backup modules
- Update command files to work with new API
- Maintain backward compatibility via connection property
```

**Feature addition:**

```
Add proposal schema with Pydantic model and migrations

Create database schema for proposals with fields:
- client_name, project_name (TEXT, NOT NULL)
- value_add_factor, estimated_timeline_months (REAL)
- hourly_rate (TEXT for currency precision)
- start_date (TEXT, flexible format)
- Timestamps: created_at, updated_at

Uses sqlite-migrate for schema versioning and sqlite-utils
for table operations. Includes migration command and status
checking.
```

**Bug fix:**

```
Fix query command to handle empty result sets correctly

The query command was failing when no results were returned
because it tried to access results[0].keys() on an empty
list. Now checks if results exist before accessing.

Also fixes JSON output to work with dict results from
sqlite-utils instead of Row objects.
```

**Refactoring:**

```
Refactor SQLite modules to use sqlite-utils Database API

Replace manual sqlite3 connection management with sqlite-utils
Database class. Benefits:
- Less boilerplate (no manual row_factory, PRAGMA statements)
- Better API for table operations
- Consistent with proposal migrations using sqlite-utils
- Easier to maintain single library vs custom wrappers
```

### What Makes a Good Commit Message

**DO:**

- Be specific about what changed
- Explain the "why" for non-obvious changes
- Reference related issues or context
- Use present tense ("Add feature" not "Added feature")
- Break down large changes into logical commits
- Include scope when helpful: "Add migrate command to proposal group"

**DON'T:**

- Use vague messages: "Fixed stuff", "Updates", "WIP"
- Write messages that only you will understand later
- Mix unrelated changes in one commit
- Use past tense: "Added feature" (use "Add feature")
- Write messages longer than 72 chars on first line
- Forget to explain non-obvious decisions

### Examples to Avoid

❌ `Fixed stuff`
❌ `Updates`
❌ `WIP`
❌ `Changed things`
❌ `Fixed bug`
❌ `Refactored code`

✅ `Fix query command to handle empty result sets`
✅ `Add proposal schema with Pydantic model and migrations`
✅ `Refactor SQLite modules to use sqlite-utils Database API`
✅ `Update gitignore to exclude database files`
✅ `Fix import sorting in sqlite modules`

## Project-Specific Notes

- Uses `uv` for package management (not `pip`)
- Ruff configuration in `pyproject.toml`
- Import sorting uses `lines-between-types = 1`
