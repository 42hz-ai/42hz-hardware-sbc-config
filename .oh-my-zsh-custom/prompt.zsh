echo "prompt.zsh"
function venv_prompt() {
    if [[ -n "$VIRTUAL_ENV" ]]; then
        echo "(py$(python --version | awk '{print $2}' | cut -d. -f1,2)) "
    fi
}

export PROMPT='$(venv_prompt)%F{green}%n@%m%f %F{blue}%~%f %# '
