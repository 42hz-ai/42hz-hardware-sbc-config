---
name: git-create-feature-branch
description: Creates new feature branches from main using feat/x naming convention. Use when starting new features, adding functionality, or when the user wants to create a feature branch, start a new feature, or mentions feat/ branches.
---

# Creating Feature Branches

## Workflow

When creating a new feature branch:

1. **Ensure you're starting from main**: Switch to main and pull latest changes
2. **Get the feature name**: Prompt the user for a descriptive feature name
3. **Create the branch**: Use `feat/feature-name` format
4. **Switch to the new branch**: Checkout the newly created branch

## Naming Conventions

Feature branches follow this pattern:

- **Format**: `feat/feature-name`
- **Prefix**: Always use `feat/` for feature branches
- **Name**: Use kebab-case (lowercase with hyphens)
- **Descriptive**: Name should clearly describe what the feature does

**Good examples:**

- `feat/user-authentication`
- `feat/database-migrations`
- `feat/payment-integration`
- `feat/dark-mode-toggle`

**Avoid:**

- `feat/feature` (too vague)
- `feat/userAuth` (use kebab-case, not camelCase)
- `feat/FEATURE` (use lowercase)
- `feat/my changes` (no spaces, use hyphens)

## Step-by-Step Process

### 1. Switch to main branch

```bash
git checkout main
```

### 2. Pull latest changes

```bash
git pull origin main
```

### 3. Prompt for feature name

Ask the user: "What would you like to name this feature branch?"

Wait for their response, then:

- Convert to kebab-case if needed (lowercase, replace spaces/special chars with hyphens)
- Validate it's descriptive (not just "feature" or "changes")
- Suggest improvements if the name is vague

### 4. Create and switch to the branch

```bash
git checkout -b feat/feature-name
```

Replace `feature-name` with the user's input (converted to kebab-case).

## Example Interaction

**User**: "Let's start a new feature branch"

**Agent**:

1. Switches to main: `git checkout main`
2. Pulls latest: `git pull origin main`
3. Asks: "What would you like to name this feature branch?"

**User**: "database migrations"

**Agent**:

- Converts to kebab-case: `database-migrations`
- Creates branch: `git checkout -b feat/database-migrations`
- Confirms: "Created and switched to feature branch 'feat/database-migrations'"

## Validation Rules

Before creating the branch, ensure:

- [ ] Feature name is provided (not empty)
- [ ] Name is descriptive (not just "feature", "changes", "stuff")
- [ ] Name is converted to kebab-case
- [ ] Branch name follows `feat/feature-name` format

If the user provides a vague name, suggest a more specific one:

- "feature" → suggest asking what the feature does
- "changes" → suggest asking what changes are being made
- "updates" → suggest asking what is being updated

## Notes

- Always start from `main` to ensure the feature branch is based on the latest code
- If the user is already on a feature branch, warn them before switching to main
- If the branch already exists, inform the user and ask if they want to switch to it instead
