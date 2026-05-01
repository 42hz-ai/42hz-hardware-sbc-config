#!/bin/bash
# sessionStart hook: verify AWS + CDK + GitHub CLI readiness for the
# 42hz-hardware-sbc-config IoT hello-world stack.
#
# This hook is workload-oriented: it NEVER requires [profile management].
# SSO is verified only when a non-management workload profile is present.
# Deploy docs: docs/SBCC-INFRA-0001-iot-hello-world-cdk.md

MGMT_ACCOUNT="719279823904"
problems=()

# --- AWS CLI ---

if ! command -v aws &>/dev/null; then
  problems+=("**AWS CLI is not installed.** Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html or rebuild the devcontainer.")
fi

# --- CDK CLI ---

if ! command -v cdk &>/dev/null; then
  if ! npx aws-cdk --version &>/dev/null 2>&1; then
    problems+=("**CDK CLI is not installed.** Run \`npm install -g aws-cdk\` or rebuild the devcontainer.")
  fi
fi

# --- GitHub CLI ---

if ! command -v gh &>/dev/null; then
  problems+=("**GitHub CLI (\`gh\`) is not installed.** Install: https://cli.github.com/")
elif ! gh auth status &>/dev/null 2>&1; then
  problems+=("**GitHub CLI is not authenticated.** Run: \`gh auth login\`")
fi

# --- SSO session (workload profile only) ---
#
# Find any profile whose sso_account_id is NOT the management account.
# Skip silently if no such profile exists (developer may not have configured
# one yet — see .devcontainer/aws-config.example).
if command -v aws &>/dev/null && [ -f ~/.aws/config ]; then
  workload_profile=""
  current_profile=""
  while IFS= read -r line; do
    if [[ "$line" =~ ^\[profile[[:space:]]+([^]]+)\] ]]; then
      current_profile="${BASH_REMATCH[1]}"
    elif [[ "$line" =~ ^sso_account_id[[:space:]]*=[[:space:]]*([0-9]+) ]]; then
      account_id="${BASH_REMATCH[1]}"
      if [ "$account_id" != "$MGMT_ACCOUNT" ] && [ -n "$current_profile" ]; then
        workload_profile="$current_profile"
        break
      fi
    fi
  done < ~/.aws/config

  if [ -n "$workload_profile" ]; then
    if ! aws sts get-caller-identity --profile "$workload_profile" &>/dev/null 2>&1; then
      problems+=("**AWS SSO session expired or not started** (profile: \`$workload_profile\`). Run: \`aws sso login --profile $workload_profile --use-device-code\`  Then: \`export AWS_PROFILE=$workload_profile\`  See: [SBCC-INFRA-0001](docs/SBCC-INFRA-0001-iot-hello-world-cdk.md)")
    fi
  fi
fi

# --- Output ---

if [ ${#problems[@]} -eq 0 ]; then
  exit 0
fi

msg="## 42hz hardware SBC config — dev environment check\n\n"
for p in "${problems[@]}"; do
  msg+="- ${p}\n"
done
msg+="\n**Deploy setup:** [SBCC-INFRA-0001](docs/SBCC-INFRA-0001-iot-hello-world-cdk.md) — SSO: [IDCTR-INFRA-0002](../iotea-infrastructure-identity-center/docs/IDCTR-INFRA-0002-aws-identity-center-cdk.md)"

jq -n --arg m "$msg" '{ "agent_message": $m }'
