#!/usr/bin/env bash
# CX Terminal: Remove a collaborator from all org repos and block them
# Usage: ./remove-collaborator.sh <username> [org]

set -euo pipefail

USERNAME="${1:?Usage: $0 <github-username> [org-name]}"
ORG="${2:-cxlinux-ai}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== CX Linux: Collaborator Removal Script ===${NC}"
echo -e "Target user: ${RED}${USERNAME}${NC}"
echo -e "Organization: ${ORG}"
echo ""

# Check gh is available and authenticated
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: gh CLI not installed. Install from https://cli.github.com${NC}"
    exit 1
fi

if ! gh auth status &> /dev/null; then
    echo -e "${RED}Error: Not authenticated. Run 'gh auth login' first.${NC}"
    exit 1
fi

echo -e "${YELLOW}[1/5] Checking org membership...${NC}"
if gh api "orgs/${ORG}/members/${USERNAME}" &> /dev/null; then
    echo -e "  Found ${RED}${USERNAME}${NC} as org member."
else
    echo -e "  ${USERNAME} is not an org member (may still be a direct collaborator on repos)."
fi

echo ""
echo -e "${YELLOW}[2/5] Scanning all repos for collaborator access...${NC}"
REPOS=$(gh repo list "${ORG}" --limit 200 --json name -q '.[].name')
FOUND_IN=()

for repo in ${REPOS}; do
    if gh api "repos/${ORG}/${repo}/collaborators/${USERNAME}" &> /dev/null 2>&1; then
        PERMISSION=$(gh api "repos/${ORG}/${repo}/collaborators/${USERNAME}/permission" --jq '.permission' 2>/dev/null || echo "unknown")
        echo -e "  ${RED}FOUND${NC} in ${ORG}/${repo} (permission: ${PERMISSION})"
        FOUND_IN+=("${repo}")
    fi
done

if [ ${#FOUND_IN[@]} -eq 0 ]; then
    echo -e "  ${GREEN}No direct collaborator access found on any repo.${NC}"
else
    echo -e "  Found access on ${RED}${#FOUND_IN[@]}${NC} repo(s)."
fi

echo ""
echo -e "${YELLOW}[3/5] Checking for open PRs and issues from ${USERNAME}...${NC}"
for repo in ${REPOS}; do
    OPEN_PRS=$(gh api "repos/${ORG}/${repo}/pulls?state=open" --jq "[.[] | select(.user.login==\"${USERNAME}\")] | length" 2>/dev/null || echo "0")
    OPEN_ISSUES=$(gh api "repos/${ORG}/${repo}/issues?state=open&creator=${USERNAME}" --jq 'length' 2>/dev/null || echo "0")
    if [ "${OPEN_PRS}" -gt 0 ] || [ "${OPEN_ISSUES}" -gt 0 ]; then
        echo -e "  ${ORG}/${repo}: ${OPEN_PRS} open PR(s), ${OPEN_ISSUES} open issue(s)"
    fi
done

echo ""
echo -e "${YELLOW}[4/5] Checking pending invitations...${NC}"
for repo in ${REPOS}; do
    INVITES=$(gh api "repos/${ORG}/${repo}/invitations" --jq "[.[] | select(.invitee.login==\"${USERNAME}\")] | .[].id" 2>/dev/null || true)
    for invite_id in ${INVITES}; do
        echo -e "  ${RED}Pending invite found${NC} on ${ORG}/${repo} (id: ${invite_id})"
    done
done

# Confirm before taking action
echo ""
echo -e "${RED}=== ACTIONS TO TAKE ===${NC}"
echo "  1. Remove ${USERNAME} from org '${ORG}' (if member)"
echo "  2. Remove ${USERNAME} as collaborator from ${#FOUND_IN[@]} repo(s)"
echo "  3. Cancel any pending invitations"
echo "  4. Block ${USERNAME} from interacting with your repos"
echo ""
read -p "Proceed? (y/N): " CONFIRM

if [[ "${CONFIRM}" != "y" && "${CONFIRM}" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo -e "${YELLOW}Removing from organization...${NC}"
gh api -X DELETE "orgs/${ORG}/members/${USERNAME}" 2>/dev/null && \
    echo -e "  ${GREEN}Removed from org.${NC}" || \
    echo -e "  Not an org member (skipped)."

echo -e "${YELLOW}Removing from repos...${NC}"
for repo in "${FOUND_IN[@]}"; do
    gh api -X DELETE "repos/${ORG}/${repo}/collaborators/${USERNAME}" 2>/dev/null && \
        echo -e "  ${GREEN}Removed from ${ORG}/${repo}${NC}" || \
        echo -e "  ${RED}Failed to remove from ${ORG}/${repo}${NC}"
done

echo -e "${YELLOW}Cancelling pending invitations...${NC}"
for repo in ${REPOS}; do
    INVITES=$(gh api "repos/${ORG}/${repo}/invitations" --jq "[.[] | select(.invitee.login==\"${USERNAME}\")] | .[].id" 2>/dev/null || true)
    for invite_id in ${INVITES}; do
        gh api -X DELETE "repos/${ORG}/${repo}/invitations/${invite_id}" 2>/dev/null && \
            echo -e "  ${GREEN}Cancelled invite on ${ORG}/${repo}${NC}" || \
            echo -e "  ${RED}Failed to cancel invite on ${ORG}/${repo}${NC}"
    done
done

echo -e "${YELLOW}Blocking user...${NC}"
gh api -X PUT "user/blocks/${USERNAME}" 2>/dev/null && \
    echo -e "  ${GREEN}${USERNAME} is now blocked.${NC}" || \
    echo -e "  ${RED}Failed to block (you may need to do this manually in GitHub settings).${NC}"

echo ""
echo -e "${GREEN}=== DONE ===${NC}"
echo "Summary:"
echo "  - Removed from org: ${ORG}"
echo "  - Removed from ${#FOUND_IN[@]} repo(s)"
echo "  - Blocked from future interaction"
echo ""
echo "If this person is making threats, also report to:"
echo "  https://support.github.com/contact/report-abuse"
