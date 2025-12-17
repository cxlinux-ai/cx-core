# pay-bounty.md

**allowed-tools:** Bash(cat:*), Bash(echo:*), Bash(grep:*), Bash(gh issue comment:*), Bash(gh pr comment:*)
**description:** Record and track bounty payments for Cortex Linux

## Context

* Payment details: $ARGUMENTS
* Bounty tracker location: `~/cortex/data/bounty-payments.csv`

## Your Task

Record a bounty payment and update tracking.

## Payment Workflow

### Step 1: Gather Payment Info

Required information:
- PR number that was merged
- Contributor GitHub username
- Bounty amount ($)
- Payment method (crypto/PayPal/Venmo)
- Payment reference (tx hash or confirmation)

### Step 2: Update CSV Tracker

```bash
echo "$DATE,$PR_NUMBER,$USERNAME,$AMOUNT,$METHOD,$TX_REF,$STATUS" >> ~/cortex/data/bounty-payments.csv
```

CSV Format:
```
date,pr,contributor,amount,method,reference,status
2024-12-16,213,pavanimanchala53,100,btc,tx_abc123,paid
2024-12-16,299,Sahilbhatane,75,paypal,PP-xyz789,paid
```

### Step 3: Comment on PR

```bash
gh pr comment $PR_NUMBER --repo cortexlinux/cortex --body "💰 **Bounty Paid**

Amount: \$$AMOUNT
Method: $METHOD
Reference: \`$TX_REF\`

Thanks for contributing to Cortex Linux! 🚀"
```

### Step 4: Discord Confirmation

Post in #payments:
```
💰 **Bounty Paid**
PR: #$PR_NUMBER
Contributor: @$USERNAME
Amount: $XX
Method: [crypto/PayPal]

Total paid to date: $XXX
```

## Payment Methods

| Method | How to Pay | Reference Format |
|--------|------------|------------------|
| Bitcoin | tip.cc bot or direct | tx hash |
| USDC | tip.cc bot or direct | tx hash |
| PayPal | paypal.me link | PP-[confirmation] |
| Venmo | @username | Venmo-[last4] |

## View Outstanding Bounties

```bash
# List all pending payments
grep ",pending" ~/cortex/data/bounty-payments.csv

# Sum pending amounts
grep ",pending" ~/cortex/data/bounty-payments.csv | awk -F',' '{sum += $4} END {print "Total pending: $" sum}'

# List by contributor
grep "$USERNAME" ~/cortex/data/bounty-payments.csv
```

## View Payment History

```bash
# All paid bounties
grep ",paid" ~/cortex/data/bounty-payments.csv

# Total paid
grep ",paid" ~/cortex/data/bounty-payments.csv | awk -F',' '{sum += $4} END {print "Total paid: $" sum}'

# Paid this month
grep "$(date +%Y-%m)" ~/cortex/data/bounty-payments.csv | grep ",paid"
```

## Bounty Ledger Report

Generate summary:
```bash
echo "## Cortex Linux Bounty Report"
echo ""
echo "### Totals"
echo "- Paid: \$$(grep ',paid' ~/cortex/data/bounty-payments.csv | awk -F',' '{sum+=$4}END{print sum}')"
echo "- Pending: \$$(grep ',pending' ~/cortex/data/bounty-payments.csv | awk -F',' '{sum+=$4}END{print sum}')"
echo ""
echo "### Top Contributors"
awk -F',' 'NR>1 {a[$3]+=$4} END {for(i in a) print a[i], i}' ~/cortex/data/bounty-payments.csv | sort -rn | head -5
```

## Post-Funding Bonus Tracking

When funding closes, run:
```bash
# Calculate 2x bonus for all contributors
awk -F',' 'NR>1 {print $3": $"$4" + $"$4" bonus = $"($4*2)}' ~/cortex/data/bounty-payments.csv
```

## Output Format

```
## Payment Recorded

**PR:** #$PR_NUMBER
**Contributor:** @$USERNAME
**Amount:** $$AMOUNT
**Method:** $METHOD
**Reference:** $TX_REF
**Status:** ✅ Paid

**Updated:** bounty-payments.csv
**Commented:** PR #$PR_NUMBER
**Discord:** Posted to #payments

---
**Running Totals:**
- Total Paid: $XXX
- Total Pending: $XXX
- Contributors Paid: XX
```
