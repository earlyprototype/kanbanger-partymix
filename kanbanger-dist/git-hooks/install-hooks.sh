#!/bin/bash
# Install Kanbanger Git Hooks

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GIT_HOOKS_DIR=".git/hooks"

echo "================================================"
echo "  Kanbanger Git Hooks Installer"
echo "================================================"
echo ""

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    echo "❌ ERROR: Not a git repository"
    echo ""
    echo "Run this from your project root (where .git/ exists)"
    exit 1
fi

echo "Installing git hooks..."
echo ""

# Install pre-commit hook
if [ -f "$GIT_HOOKS_DIR/pre-commit" ]; then
    echo "⚠️  pre-commit hook already exists"
    read -p "Overwrite? (y/N): " answer
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        echo "Skipping pre-commit hook"
    else
        cp "$SCRIPT_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit"
        chmod +x "$GIT_HOOKS_DIR/pre-commit"
        echo "✓ pre-commit hook installed"
    fi
else
    cp "$SCRIPT_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit"
    chmod +x "$GIT_HOOKS_DIR/pre-commit"
    echo "✓ pre-commit hook installed"
fi

echo ""

# Install post-commit hook
if [ -f "$GIT_HOOKS_DIR/post-commit" ]; then
    echo "⚠️  post-commit hook already exists"
    read -p "Overwrite? (y/N): " answer
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        echo "Skipping post-commit hook"
    else
        cp "$SCRIPT_DIR/post-commit" "$GIT_HOOKS_DIR/post-commit"
        chmod +x "$GIT_HOOKS_DIR/post-commit"
        echo "✓ post-commit hook installed"
    fi
else
    cp "$SCRIPT_DIR/post-commit" "$GIT_HOOKS_DIR/post-commit"
    chmod +x "$GIT_HOOKS_DIR/post-commit"
    echo "✓ post-commit hook installed"
fi

echo ""
echo "================================================"
echo "  Installation Complete!"
echo "================================================"
echo ""
echo "Hooks installed:"
echo "  - pre-commit: Checks kanban is synced before commits"
echo "  - post-commit: Auto-syncs kanban after commits"
echo ""
echo "Test the hooks by making a commit!"
echo ""
