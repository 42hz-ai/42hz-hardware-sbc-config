alias gc='git commit'
alias gp='git push'

function branches() {
  git for-each-ref --sort=-committerdate refs/heads/ | grep /ts | awk '{print $3}' |  sed 's|refs/heads/||g'
}

function branches_all() {
  git for-each-ref --sort=-committerdate refs/heads/ | awk '{print $3}' |  sed 's|refs/heads/||g'
}


function delete_current_branch () {
  go_to=${1-master}
  CURR_BRANCH=`git rev-parse --abbrev-ref HEAD`

  echo $CURR_BRANCH

  if [[ "$CURR_BRANCH" == 'main' ]]; then
    echo 'can not delete main branch'
    exit 1
  fi

  if [[ "$CURR_BRANCH" == 'development' ]]; then
    echo 'can not delete development branch'
    exit 1
  fi


  git checkout "$go_to"
  git branch -D $CURR_BRANCH

}

function gpush() {
  gc .; gp origin $(git rev-parse --symbolic-full-name --abbrev-ref HEAD)
}

function gpushf() {
  gc .; gp origin $(git rev-parse --symbolic-full-name --abbrev-ref HEAD) -f
}

function gpull() {
  gc .; git pull origin $(git rev-parse --symbolic-full-name --abbrev-ref HEAD)
}

function gpusho(){
  git add "$@"; git commit "$@"; gp origin "$(git rev-parse --symbolic-full-name --abbrev-ref HEAD)"
}
