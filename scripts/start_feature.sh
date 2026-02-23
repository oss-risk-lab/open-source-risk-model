#!/bin/bash
# Helper script to start a new feature branch

if [ -z "$1" ]; then
    echo "Usage: ./scripts/start_feature.sh <feature-name>"
    echo "Example: ./scripts/start_feature.sh phase-c-package-resolution"
    exit 1
fi

FEATURE_NAME=$1
BRANCH_NAME="feature/$FEATURE_NAME"

echo "🚀 Starting new feature: $FEATURE_NAME"
echo ""

# Make sure we're on main and up to date
echo "📥 Updating main branch..."
git checkout main
git pull origin main

# Create and checkout new feature branch
echo "🌿 Creating feature branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME"

echo ""
echo "✅ Feature branch created!"
echo ""
echo "Next steps:"
echo "  1. Make your changes"
echo "  2. git add <files>"
echo "  3. git commit -m 'your message'"
echo "  4. git push origin $BRANCH_NAME"
echo "  5. Create PR on GitHub"
echo ""
echo "Or use: ./scripts/finish_feature.sh to commit and push"
