#!/bin/bash
# fetch-fork-emails.sh
# Fetches public email addresses from Cortex fork contributors
# Usage: ./fetch-fork-emails.sh

echo "═══════════════════════════════════════════════════════════════════"
echo "  CORTEX FORK CONTRIBUTOR EMAIL FETCHER"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

OUTPUT_FILE="fork-contributor-contacts.csv"
echo "username,email,name,company,location,twitter,blog,bio" > "$OUTPUT_FILE"

# Get all fork owners
echo "📥 Fetching fork contributors..."
echo ""

FORKS=$(curl -s "https://api.github.com/repos/cortexlinux/cortex/forks?per_page=100" | jq -r '.[].owner.login')

for username in $FORKS; do
    echo -n "→ $username: "

    # Fetch user profile
    USER_DATA=$(curl -s "https://api.github.com/users/$username")

    EMAIL=$(echo "$USER_DATA" | jq -r '.email // "N/A"')
    NAME=$(echo "$USER_DATA" | jq -r '.name // "N/A"')
    COMPANY=$(echo "$USER_DATA" | jq -r '.company // "N/A"')
    LOCATION=$(echo "$USER_DATA" | jq -r '.location // "N/A"')
    TWITTER=$(echo "$USER_DATA" | jq -r '.twitter_username // "N/A"')
    BLOG=$(echo "$USER_DATA" | jq -r '.blog // "N/A"')
    BIO=$(echo "$USER_DATA" | jq -r '.bio // "N/A"' | tr ',' ';' | tr '\n' ' ')

    # Try to get email from recent commits if not in profile
    if [ "$EMAIL" = "N/A" ] || [ "$EMAIL" = "null" ]; then
        COMMIT_EMAIL=$(curl -s "https://api.github.com/users/$username/events/public" | \
            jq -r '[.[] | select(.type=="PushEvent") | .payload.commits[]?.author.email] | first // "N/A"')
        if [ "$COMMIT_EMAIL" != "N/A" ] && [ "$COMMIT_EMAIL" != "null" ] && [[ ! "$COMMIT_EMAIL" =~ "noreply" ]]; then
            EMAIL="$COMMIT_EMAIL"
        fi
    fi

    echo "$username,$EMAIL,$NAME,$COMPANY,$LOCATION,$TWITTER,$BLOG,\"$BIO\"" >> "$OUTPUT_FILE"

    if [ "$EMAIL" != "N/A" ] && [ "$EMAIL" != "null" ]; then
        echo "✓ Found email: $EMAIL"
    else
        echo "○ No public email (check Twitter: $TWITTER, Blog: $BLOG)"
    fi

    sleep 0.5  # Rate limiting
done

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  SUMMARY"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
TOTAL=$(echo "$FORKS" | wc -l | tr -d ' ')
WITH_EMAIL=$(grep -v "N/A" "$OUTPUT_FILE" | grep -v "null" | grep "@" | wc -l | tr -d ' ')
echo "Total contributors: $TOTAL"
echo "With public email: $WITH_EMAIL"
echo ""
echo "✅ Results saved to: $OUTPUT_FILE"
echo ""

# Display results
echo "═══════════════════════════════════════════════════════════════════"
echo "  CONTACT DETAILS"
echo "═══════════════════════════════════════════════════════════════════"
column -t -s',' "$OUTPUT_FILE" | head -20
