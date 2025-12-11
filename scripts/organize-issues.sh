#!/bin/bash
# Label and organize issues for MVP focus

set -e

echo "🎯 ORGANIZING ISSUES FOR MVP FOCUS"
echo "====================================="

cd ~/cortex

echo "Strategy:"
echo "  Issues #1-30: MVP Critical"
echo "  Issues #31-45: MVP Nice-to-Have"  
echo "  Issues #46+: Post-MVP"
echo ""

read -p "Organize all issues? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Create milestones
echo "📋 Creating milestones..."
gh api repos/cortexlinux/cortex/milestones --method POST \
    -f title='MVP - Core Features' \
    -f description='Critical features required for MVP launch' 2>/dev/null || echo "  MVP milestone exists"

gh api repos/cortexlinux/cortex/milestones --method POST \
    -f title='Post-MVP - Enhancements' \
    -f description='Features for post-MVP releases' 2>/dev/null || echo "  Post-MVP milestone exists"

echo ""
echo "🏷️  Labeling MVP Critical (#1-30)..."
for i in {1..30}; do
    gh issue edit $i --add-label "mvp-critical,priority: critical" --milestone "MVP - Core Features" 2>/dev/null && echo "  ✅ #$i" || echo "  ⚠️  #$i not found"
    sleep 0.3
done

echo ""
echo "🏷️  Labeling Post-MVP (#46-150)..."
for i in {46..150}; do
    gh issue edit $i --add-label "post-mvp" --milestone "Post-MVP - Enhancements" 2>/dev/null
    (( i % 20 == 0 )) && echo "  Processed through #$i..." && sleep 1
done

echo ""
echo "✅ COMPLETE!"
echo ""
echo "View MVP Critical: https://github.com/cortexlinux/cortex/issues?q=is%3Aopen+label%3Amvp-critical"
