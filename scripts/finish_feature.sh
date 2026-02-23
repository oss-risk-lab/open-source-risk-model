#!/bin/bash
# Helper script to finish a feature branch and create PR

if [ -z "$1" ]; then
    echo "Usage: ./scripts/finish_feature.sh <commit-message>"
    echo "Example: ./scripts/finish_feature.sh 'feat: Add package resolution (Phase C)'"
    exit 1
fi

COMMIT_MSG=$1
CURRENT_BRANCH=$(git branch --show-current)

if [ "$CURRENT_BRANCH" = "main" ]; then
    echo "❌ Error: You're on main branch. Switch to a feature branch first."
    echo "Use: ./scripts/start_feature.sh <feature-name>"
    exit 1
fi

echo "🔍 Current branch: $CURRENT_BRANCH"
echo ""

# Show what will be committed
echo "📝 Files to be committed:"
git status --short
echo ""

read -p "Continue with commit? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted"
    exit 1
fi

# Stage all changes
echo "📦 Staging changes..."
git add -A

# Commit
echo "💾 Committing..."
git commit -m "$COMMIT_MSG"

# Push
echo "🚀 Pushing to origin..."
git push origin "$CURRENT_BRANCH"

echo ""
echo "✅ Feature branch pushed!"
echo ""
echo "🔗 Create Pull Request:"
echo "   https://github.com/oss-risk-lab/open-source-risk-model/compare/$CURRENT_BRANCH?expand=1"
echo ""
echo "Or merge directly to main:"
echo "   git checkout main"
echo "   git merge $CURRENT_BRANCH"
echo "   git push origin main"
