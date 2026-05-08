#!/bin/bash

set -e


# Colors for pretty output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# sbc imaging: guestfish / virt-copy-in (image may predate Dockerfile RUN layer)
if ! command -v guestfish >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    echo -e "${BLUE}Installing libguestfs-tools for sbc imaging...${NC}"
    apt-get update
    apt-get install -y libguestfs-tools openssl xz-utils
    rm -rf /var/lib/apt/lists/*
fi

if [ ! -d ".git" ]; then
    echo -e "${BLUE}Initializing git repository...${NC}"
    # Must run before git init; configure_git.sh is not sourced by this script.
    git config --global init.defaultBranch main
    git init
fi

# Install oh-my-zsh if not already installed
echo -e "${BLUE}Installing oh-my-zsh...${NC}"

if [ ! -d "$HOME/.oh-my-zsh" ]; then
    echo -e "${BLUE}Installing oh-my-zsh...${NC}"
    sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

    # Install additional zsh plugins
    echo -e "${BLUE}Installing additional zsh plugins...${NC}"
    git clone https://github.com/zsh-users/zsh-autosuggestions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-autosuggestions
    git clone https://github.com/zsh-users/zsh-syntax-highlighting.git ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting
    git clone https://github.com/zsh-users/zsh-completions ${ZSH_CUSTOM:-~/.oh-my-zsh/custom}/plugins/zsh-completions

    # Configure oh-my-zsh plugins
    sed -i 's/plugins=(git)/plugins=(git python pip docker docker-compose aws zsh-autosuggestions zsh-syntax-highlighting zsh-completions)/' ~/.zshrc
else
    echo -e "${BLUE}oh-my-zsh already installed${NC}"
fi

# Always check and update theme if it's devcontainers
if grep -q 'ZSH_THEME="devcontainers"' ~/.zshrc; then
    echo -e "${BLUE}Updating ZSH theme to robbyrussell...${NC}"
    sed -i 's/ZSH_THEME="devcontainers"/ZSH_THEME="robbyrussell"/' ~/.zshrc
fi

# Continue with the rest of the setup
# One venv with all optional extras (CDK, lint, dev, mqtt/iot, notion) so hooks
# and `cdk`/ruff work without a second `uv sync`.
uv sync --all-extras
uv run pre-commit install

# ~/.zshrc is recreated on each devcontainer rebuild; repopulate persisted bits by marker match.
SBCC_HIST_REL=".sbcc/terminal/zsh_history"
mkdir -p "${PWD}/${SBCC_HIST_REL%/*}"
touch "${PWD}/${SBCC_HIST_REL}"
SBCC_HIST_ABS="${PWD}/${SBCC_HIST_REL}"
HIST_MARKER="# SBCC: persisted zsh history (workspace)"
if [[ -f ~/.zshrc ]] && ! grep -Fq "${HIST_MARKER}" ~/.zshrc 2>/dev/null; then
    printf '\n%s\nexport HISTFILE=%q\nexport HISTSIZE=50000 SAVEHIST=50000\n' \
        "${HIST_MARKER}" "${SBCC_HIST_ABS}" >> ~/.zshrc
fi

# Optional `.devcontainer/env.local` — copy from `env.local.sample`; gitignored exports that survive rebuilds.
ENV_MARKER="# SBCC: workspace .devcontainer/env.local (optional)"
if [[ -f ~/.zshrc ]] && ! grep -Fq "${ENV_MARKER}" ~/.zshrc 2>/dev/null; then
    cat >>~/.zshrc <<'SBCC_ENV_SNIP'

# SBCC: workspace .devcontainer/env.local (optional)
if sbcc_git_root="$(git rev-parse --show-toplevel 2>/dev/null)" && [[ -n "${sbcc_git_root}" ]] && [[ -r "${sbcc_git_root}/.devcontainer/env.local" ]]; then
    # shellcheck source=/dev/null
    source "${sbcc_git_root}/.devcontainer/env.local"
fi
unset -v sbcc_git_root

SBCC_ENV_SNIP
fi

# Add aliases to zshrc
printf "\nalias ll='ls -lahSr --color=auto'\n" >> ~/.zshrc

# Run ruff with native server
uv run ruff check --select I,F401 --fix --exit-zero
uv run ruff format

if [ ! -L ~/.oh-my-zsh/custom ]; then
    echo -e "${BLUE}Creating symlink for oh-my-zsh custom directory...${NC}"
    # Remove existing directory if it exists
    if [ -d ~/.oh-my-zsh/custom ]; then
        rm -rf ~/.oh-my-zsh/custom
    fi
    ln -s "${PWD}/.oh-my-zsh-custom" ~/.oh-my-zsh/custom
else
    echo -e "${BLUE}oh-my-zsh custom directory already exists${NC}"
fi

# Remind about Python interpreter selection
echo -e "\n${YELLOW}IMPORTANT: Remember to select your Python interpreter:${NC}"
echo -e "1. Press ${GREEN}Cmd/Ctrl + Shift + P${NC}"
echo -e "2. Type ${GREEN}Python: Select Interpreter${NC}"
echo -e "3. Choose the interpreter from ${GREEN}.venv/bin/python${NC}\n"
