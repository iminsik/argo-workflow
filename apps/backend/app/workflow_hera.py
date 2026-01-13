"""
Workflow Creation with Hera SDK

This module provides workflow creation functionality using Hera SDK,
simplifying the process compared to YAML template manipulation.

Usage:
1. Install hera-workflows: pip install hera-workflows
2. Use create_workflow_with_hera() in your workflow creation logic
"""

import os
from typing import Optional
from hera.workflows import Workflow, Script, Container, Parameter
from hera.workflows.models import VolumeMount, Volume, EnvVar, PersistentVolumeClaimVolumeSource
from kubernetes.client import CoreV1Api, CustomObjectsApi  # type: ignore
from fastapi import HTTPException


def build_script_source(
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None,
    system_dependencies: Optional[str] = None,
    use_cache: bool = True
) -> str:
    """
    Build the bash script source for executing Python code with optional dependencies.
    
    This replaces the complex YAML template manipulation and requirements file injection.
    
    Args:
        dependencies: Python package names (space or comma-separated)
        requirements_file: requirements.txt content
        system_dependencies: Nix package names (space or comma-separated, e.g., "gcc make")
        use_cache: Whether to use UV and Nix caches (default: True)
    
    Note: The Python code is passed via the PYTHON_CODE environment variable,
    which is set separately when creating the workflow template.
    """
    script_parts = [
        "set -e",
        "",
    ]
    
    # Install system dependencies using nix-portable (if provided)
    if system_dependencies:
        script_parts.extend([
            "# Install system dependencies using nix-portable",
            "if ! command -v nix-portable &> /dev/null; then",
            "  echo 'Error: nix-portable not found in image. Using nix-portable base image required.'",
            "  exit 1",
            "fi",
            "",
        ])
        
        # Configure nix-portable to use shared PVC store if cache is enabled
        if use_cache:
            script_parts.extend([
                "# PVC is mounted directly to ~/.nix-portable/nix/store - no copying needed!",
                "# This eliminates rsync/cp overhead - packages are directly accessible",
                "export NP_STORE=~/.nix-portable/nix/store",
                "  ",
                "# Create symlink for backward compatibility with scripts that reference /nix/store",
                "mkdir -p /nix",
                "rm -f /nix/store 2>/dev/null || true",
                "ln -sf ~/.nix-portable/nix/store /nix/store",
                "  ",
                "# Verify store is accessible",
                "if [ -w ~/.nix-portable/nix/store ]; then",
                "  echo \"Nix store is writable (mounted directly from PVC)\"",
                "else",
                "  echo \"Warning: Nix store may not be writable\"",
                "fi",
                "  ",
                "# Check available disk space before attempting downloads",
                "AVAILABLE_SPACE=$(df -BG ~/.nix-portable/nix/store 2>/dev/null | tail -1 | awk '{print $4}' | sed 's/G//' || echo 'unknown')",
                "if [ \"$AVAILABLE_SPACE\" != \"unknown\" ] && [ \"$AVAILABLE_SPACE\" -lt 1 ]; then",
                "  echo -e \"\\033[0;31m[ERROR]\\033[0m Insufficient disk space: ${AVAILABLE_SPACE}GB available\"",
                "  echo \"The Nix store PVC is full. Please free up space or increase PVC size.\"",
                "  echo \"Current usage:\"",
                "  df -h ~/.nix-portable/nix/store 2>/dev/null || true",
                "  exit 1",
                "elif [ \"$AVAILABLE_SPACE\" != \"unknown\" ]; then",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Available disk space: ${AVAILABLE_SPACE}GB\"",
                "fi",
                "  ",
                "# Set up database directory - store it in the PVC under .nix-db",
                "mkdir -p ~/.nix-portable/nix/var/nix",
                "mkdir -p ~/.nix-portable/nix/store/.nix-db",
                "# Create symlink from nix-portable's expected db location to PVC location",
                "rm -rf ~/.nix-portable/nix/var/nix/db 2>/dev/null || true",
                "ln -sf ~/.nix-portable/nix/store/.nix-db ~/.nix-portable/nix/var/nix/db",
                "  ",
                "# Count packages in store (mounted directly, no copying needed)",
                "PACKAGE_COUNT=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || echo 0)",
                "if [ $PACKAGE_COUNT -gt 0 ]; then",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Found $PACKAGE_COUNT packages in store (mounted directly, no copy needed)\"",
                "else",
                "  echo \"No packages found in store (first run)\"",
                "fi",
                "  ",
                "# Check if database exists",
                "if [ -f ~/.nix-portable/nix/store/.nix-db/db.sqlite ]; then",
                "  DB_SIZE=$(stat -c%s ~/.nix-portable/nix/store/.nix-db/db.sqlite 2>/dev/null || echo 0)",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Database found (size: $DB_SIZE bytes)\"",
                "else",
                "  echo \"Database will be created on first run (this is normal for first run)\"",
                "fi",
                "# Verify database directory is accessible and writable",
                "if [ -w ~/.nix-portable/nix/var/nix/db ]; then",
                "  echo \"Database directory is writable\"",
                "else",
                "  echo \"Warning: Database directory may not be writable\"",
                "fi",
                "  ",
                "# Count packages in nix-portable store",
                "NIX_STORE_COUNT=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || echo 0)",
                "if [ $NIX_STORE_COUNT -gt 0 ]; then",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Found $NIX_STORE_COUNT packages in nix-portable store\"",
                "fi",
                "  ",
                "# Check if database exists",
                "DB_FOUND=false",
                "if [ -f ~/.nix-portable/nix/var/nix/db/db.sqlite ]; then",
                "  DB_SIZE=$(stat -c%s ~/.nix-portable/nix/var/nix/db/db.sqlite 2>/dev/null || echo 0)",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Database found via symlink (size: $DB_SIZE bytes)\"",
                "  DB_FOUND=true",
                "elif [ -f /nix/store/.nix-db/db.sqlite ]; then",
                "  DB_SIZE=$(stat -c%s /nix/store/.nix-db/db.sqlite 2>/dev/null || echo 0)",
                "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Database found in shared store (size: $DB_SIZE bytes)\"",
                "  # Ensure symlink directory structure exists",
                "  mkdir -p ~/.nix-portable/nix/var/nix",
                "  rm -rf ~/.nix-portable/nix/var/nix/db 2>/dev/null || true",
                "  ln -sf /nix/store/.nix-db ~/.nix-portable/nix/var/nix/db",
                "  echo \"Database symlink created\"",
                "  DB_FOUND=true",
                "else",
                "  # Check if database exists in any subdirectory of shared store",
                "  DB_CANDIDATE=$(find /nix/store -name \"db.sqlite\" -type f 2>/dev/null | head -1)",
                "  if [ -n \"$DB_CANDIDATE\" ]; then",
                "    DB_SIZE=$(stat -c%s \"$DB_CANDIDATE\" 2>/dev/null || echo 0)",
                "    echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Found database at: $DB_CANDIDATE (size: $DB_SIZE bytes)\"",
                "    # Copy or symlink it to the expected location",
                "    mkdir -p /nix/store/.nix-db",
                "    cp \"$DB_CANDIDATE\" /nix/store/.nix-db/db.sqlite 2>/dev/null || true",
                "    mkdir -p ~/.nix-portable/nix/var/nix",
                "    rm -rf ~/.nix-portable/nix/var/nix/db 2>/dev/null || true",
                "    ln -sf /nix/store/.nix-db ~/.nix-portable/nix/var/nix/db",
                "    echo \"Database copied and symlinked\"",
                "    DB_FOUND=true",
                "  else",
                "    echo \"Database will be created on first run (this is normal for first run)\"",
                "  fi",
                "fi",
                "",
            ])
        
        script_parts.extend([
            'echo "Installing system dependencies: $SYSTEM_DEPS"',
            "# Convert comma-separated to space-separated",
            'SYSTEM_DEPS=$(echo "$SYSTEM_DEPS" | tr "," " ")',
            "",
            "# Check Nix store cache status",
            "if [ -n \"$NP_STORE\" ] && [ -d \"$NP_STORE\" ]; then",
            "  STORE_COUNT=$(find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
            "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Store contains $STORE_COUNT packages\"",
            "else",
            "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m No shared store configured, using local cache\"",
            "fi",
            "",
            "# Build nix-shell command with all system dependencies",
            "# We'll use nix-shell directly when executing Python code - no separate preparation needed",
            "# nix-shell will handle downloading packages if needed (fast if cached)",
            "NIX_PACKAGES=\"\"",
            "for dep in $SYSTEM_DEPS; do",
            "  NIX_PACKAGES=\"$NIX_PACKAGES -p $dep\"",
            "  echo \"System dependency: $dep (will be available via nix-shell)\"",
            "done",
            "export NIX_SHELL_PACKAGES=\"$NIX_PACKAGES\"",
            "echo \"System dependencies configured. Packages will be available when executing Python code.\"",
            "",
            "# Final cache status",
            "if [ -n \"$NP_STORE\" ] && [ -d \"$NP_STORE\" ]; then",
            "  FINAL_COUNT=$(find \"$NP_STORE\" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)",
            "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Final store count: $FINAL_COUNT packages\"",
            "fi",
            "",
            "echo 'System dependencies installed successfully'",
            "",
        ])
    
    # Install uv if not present
    script_parts.extend([
        "# Install uv if not present",
        "if ! command -v uv &> /dev/null; then",
        "  pip install --no-cache-dir uv",
        "fi",
        "",
    ])
    
    # Set UV cache directory if cache is enabled
    if use_cache:
        script_parts.extend([
            "# Use shared UV cache",
            "export UV_CACHE_DIR=/root/.cache/uv",
            "mkdir -p $UV_CACHE_DIR",
            'echo "Using UV cache at: $UV_CACHE_DIR"',
            "# Check cache status",
            "if [ -d \"$UV_CACHE_DIR\" ]; then",
            "  CACHE_SIZE=$(du -sh \"$UV_CACHE_DIR\" 2>/dev/null | cut -f1)",
            "  CACHE_FILES=$(find \"$UV_CACHE_DIR\" -type f 2>/dev/null | wc -l)",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m Cache directory size: $CACHE_SIZE ($CACHE_FILES files)\"",
            "else",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m Cache directory does not exist, will be created\"",
            "fi",
            "",
        ])
    
    # Create isolated virtual environment
    script_parts.extend([
        "# Create isolated virtual environment",
        'VENV_DIR="/tmp/venv-{{workflow.name}}"',
        'uv venv "$VENV_DIR"',
        "",
        "# Activate virtual environment",
        'source "$VENV_DIR/bin/activate"',
    ])
    
    # Handle requirements file
    if requirements_file:
        script_parts.extend([
            "",
            "# Write requirements file",
            "cat > /tmp/requirements.txt << 'REQ_EOF'",
            requirements_file,
            "REQ_EOF",
            "",
            "# Install dependencies from requirements.txt with cache logging",
            "echo 'Installing from requirements.txt...'",
            "# Check cache status before installation",
            "if [ -n \"$UV_CACHE_DIR\" ] && [ -d \"$UV_CACHE_DIR\" ]; then",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m Checking cache for packages in requirements.txt...\"",
            "  while IFS= read -r line || [ -n \"$line\" ]; do",
            "    # Skip comments and empty lines",
            "    [ -z \"$line\" ] || [ \"${line#\"#\"}\" != \"$line\" ] && continue",
            "    PKG_NAME=$(echo \"$line\" | cut -d'=' -f1 | cut -d'[' -f1 | xargs)",
            "    if [ -n \"$PKG_NAME\" ] && find \"$UV_CACHE_DIR\" -name \"*${PKG_NAME}*\" -type f 2>/dev/null | grep -q .; then",
            "      echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m $PKG_NAME found in \\033[1;32mLOCAL CACHE\\033[0m\"",
            "    elif [ -n \"$PKG_NAME\" ]; then",
            "      echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m $PKG_NAME will be downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI)\"",
            "    fi",
            "  done < /tmp/requirements.txt",
            "fi",
            "# Install packages and capture output to detect cache usage",
            "INSTALL_OUTPUT=$(uv pip install -r /tmp/requirements.txt 2>&1)",
            "INSTALL_STATUS=$?",
            "# Check if packages were downloaded or from cache",
            "if echo \"$INSTALL_OUTPUT\" | grep -q \"Downloading\"; then",
            "  DOWNLOADED_PKGS=$(echo \"$INSTALL_OUTPUT\" | grep \"Downloading\" | sed \"s/.*Downloading \\([^ ]*\\).*/\\1/\" | tr \"\\n\" \" \")",
            "  echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m Downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI): $DOWNLOADED_PKGS\"",
            "fi",
            "if echo \"$INSTALL_OUTPUT\" | grep -q \"Resolved.*in.*ms\"; then",
            "  RESOLVE_TIME=$(echo \"$INSTALL_OUTPUT\" | grep -oP 'Resolved.*in \\K[0-9]+ms' | head -1)",
            "  if [ -z \"$DOWNLOADED_PKGS\" ]; then",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m All packages from \\033[1;32mLOCAL CACHE\\033[0m (resolved in $RESOLVE_TIME)\"",
            "  fi",
            "fi",
            "if [ $INSTALL_STATUS -eq 0 ]; then",
            "  echo 'Dependencies installed successfully'",
            "else",
            "  echo 'Error installing dependencies'",
            "  echo \"$INSTALL_OUTPUT\"",
            "  exit 1",
            "fi",
        ])
    elif dependencies:
        script_parts.extend([
            "",
            "# Install Python dependencies with cache logging",
            "echo 'Installing Python packages: $PYTHON_DEPS'",
            "# Check which packages are already cached",
            "for pkg in $(echo \"$PYTHON_DEPS\" | tr ',' ' '); do",
            "  PKG_NAME=$(echo \"$pkg\" | cut -d'=' -f1 | cut -d'[' -f1)",
            "  if [ -n \"$UV_CACHE_DIR\" ] && find \"$UV_CACHE_DIR\" -name \"*${PKG_NAME}*\" -type f 2>/dev/null | grep -q .; then",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m $PKG_NAME found in \\033[1;32mLOCAL CACHE\\033[0m\"",
            "  else",
            "    echo -e \"\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m $PKG_NAME will be downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI)\"",
            "  fi",
            "done",
            "# Install packages and capture output to detect cache usage",
            'INSTALL_OUTPUT=$(echo "$PYTHON_DEPS" | tr \',\' \' \' | xargs uv pip install 2>&1)',
            'INSTALL_STATUS=$?',
            '# Check if packages were downloaded or from cache',
            'if echo "$INSTALL_OUTPUT" | grep -q "Downloading"; then',
            '  DOWNLOADED_PKGS=$(echo "$INSTALL_OUTPUT" | grep "Downloading" | sed "s/.*Downloading \\([^ ]*\\).*/\\1/" | tr "\\n" " ")',
            '  echo -e "\\033[0;36m[UV CACHE]\\033[0m \\033[0;31m✗\\033[0m Downloaded from \\033[1;31mEXTERNAL\\033[0m (PyPI): $DOWNLOADED_PKGS"',
            'fi',
            'if echo "$INSTALL_OUTPUT" | grep -q "Resolved.*in.*ms"; then',
            '  RESOLVE_TIME=$(echo "$INSTALL_OUTPUT" | grep -oP "Resolved.*in \\K[0-9]+ms" | head -1)',
            '  if [ -z "$DOWNLOADED_PKGS" ]; then',
            '    echo -e "\\033[0;36m[UV CACHE]\\033[0m \\033[0;32m✓\\033[0m All packages from \\033[1;32mLOCAL CACHE\\033[0m (resolved in $RESOLVE_TIME)"',
            '  fi',
            'fi',
            'if [ $INSTALL_STATUS -eq 0 ]; then',
            '  echo "Python dependencies installed successfully"',
            'else',
            '  echo "Error installing dependencies"',
            '  echo "$INSTALL_OUTPUT"',
            '  exit 1',
            'fi',
        ])
    
    # Execute Python code
    # Note: $PYTHON_CODE is set as an environment variable in create_workflow_with_hera()
    script_parts.extend([
        "",
        "# Execute Python code",
        "# If system dependencies are needed, wrap execution in nix-shell",
        "if [ -n \"$SYSTEM_DEPS\" ] && [ -n \"$NIX_SHELL_PACKAGES\" ]; then",
        "  echo \"Executing Python code with system dependencies available via nix-shell...\"",
        "  # Check if packages exist in store before running",
        "  STORE_PACKAGES=$(find /nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || echo 0)",
        "  echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Packages in store before execution: $STORE_PACKAGES\"",
        "  ",
        "  # Verify database exists before execution",
        "  DB_EXISTS=false",
        "  if [ -f ~/.nix-portable/nix/var/nix/db/db.sqlite ]; then",
        "    DB_EXISTS=true",
        "    echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Database exists before execution\"",
        "  elif [ -f /nix/store/.nix-db/db.sqlite ]; then",
        "    # Database exists in shared store but symlink might be broken",
        "    echo \"Database found in shared store, ensuring symlink...\"",
        "    mkdir -p ~/.nix-portable/nix/var/nix/db",
        "    rm -f ~/.nix-portable/nix/var/nix/db/db.sqlite 2>/dev/null || true",
        "    ln -sf /nix/store/.nix-db/db.sqlite ~/.nix-portable/nix/var/nix/db/db.sqlite",
        "    DB_EXISTS=true",
        "    echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Database symlink created\"",
        "  fi",
        "  ",
        "  if [ \"$DB_EXISTS\" = \"false\" ]; then",
        "    echo -e \"\\033[0;33m[NIX CACHE]\\033[0m Warning: Database does not exist\"",
        "    ",
        "    # Ensure database directory exists and is writable",
        "    mkdir -p ~/.nix-portable/nix/var/nix/db",
        "    chmod 755 ~/.nix-portable/nix/var/nix/db 2>/dev/null || true",
        "    ",
        "    # Test that we can write to the database directory (via symlink)",
        "    TEST_FILE=~/.nix-portable/nix/var/nix/db/.test-write",
        "    if touch \"$TEST_FILE\" 2>/dev/null && rm -f \"$TEST_FILE\" 2>/dev/null; then",
        "      echo \"Database directory is writable (test write succeeded)\"",
        "    else",
        "      echo \"Warning: Cannot write to database directory - this may cause issues\"",
        "    fi",
        "    ",
        "    if [ $STORE_PACKAGES -gt 0 ]; then",
        "      echo \"Packages exist ($STORE_PACKAGES) but database missing\"",
        "      echo \"nix-portable requires database to recognize packages\"",
        "      echo \"nix-portable will attempt to download packages to create database\"",
        "      echo \"Note: If download fails, check network connectivity and nix-portable configuration\"",
        "    else",
        "      echo \"No packages exist - nix-portable will download and create database\"",
        "    fi",
        "  fi",
        "  ",
        "  # Run nix-shell - it will use cached packages if they exist in the database",
        "  # If database doesn't exist, nix-portable will download packages (which creates database)",
        "  # The database will be created in ~/.nix-portable/nix/var/nix/db/db.sqlite",
        "  # which is symlinked to /nix/store/.nix-db/db.sqlite, so it will be persisted",
        "  echo \"Running nix-shell (this may download packages if database doesn't exist)...\"",
        "  ",
        "  # IMPORTANT: nix-portable requires network access to evaluate packages",
        "  # Even if packages exist on disk, it needs network to evaluate nixpkgs expressions",
        "  # Set NIX_PATH to help nix-portable find nixpkgs",
        "  export NIX_PATH=nixpkgs=https://github.com/NixOS/nixpkgs/archive/nixos-unstable.tar.gz",
        "  ",
        "  # Try to test network connectivity first",
        "  echo \"Testing network connectivity...\"",
        "  if curl -s --max-time 5 https://cache.nixos.org >/dev/null 2>&1; then",
        "    echo \"Network connectivity: OK (can reach cache.nixos.org)\"",
        "  else",
        "    echo \"Warning: Cannot reach cache.nixos.org - network may be blocked\"",
        "  fi",
        "  if curl -s --max-time 5 https://github.com >/dev/null 2>&1; then",
        "    echo \"Network connectivity: OK (can reach github.com)\"",
        "  else",
        "    echo \"Warning: Cannot reach github.com - network may be blocked\"",
        "  fi",
        "  ",
        "  # Try a simple nix-portable command first to see if it works at all",
        "  echo \"Testing nix-portable basic functionality...\"",
        "  set +e",
        "  # Run command with tee to both stream output in real-time AND capture it",
        "  # This ensures logs appear immediately even if command hangs",
        "  TEMP_OUTPUT=$(mktemp)",
        "  # Run with timeout, use tee to stream to both stdout and temp file",
        "  timeout 30 nix-portable nix --version 2>&1 | tee \"$TEMP_OUTPUT\"",
        "  NIX_TEST_EXIT=${PIPESTATUS[0]}",
        "  NIX_TEST=$(cat \"$TEMP_OUTPUT\" 2>/dev/null || echo \"\")",
        "  rm -f \"$TEMP_OUTPUT\"",
        "  set -e",
        "  if [ $NIX_TEST_EXIT -eq 0 ] && [ -n \"$NIX_TEST\" ]; then",
        "    echo \"nix-portable basic test: OK ($NIX_TEST)\"",
        "  else",
        "    echo \"nix-portable basic test: FAILED\"",
        "    if [ -n \"$NIX_TEST\" ]; then",
        "      echo \"Output: $NIX_TEST\"",
        "    fi",
        "    echo \"Exit code: $NIX_TEST_EXIT\"",
        "  fi",
        "  ",
        "  # Capture full output for debugging",
        "  echo \"Running nix-shell command...\"",
        "  echo \"=== Full nix-shell output ===\"",
        "  set +e",
        "  # Run nix-shell with tee to stream output in real-time AND capture it",
        "  # Use a longer timeout for nix-shell (5 minutes should be enough for most cases)",
        "  TEMP_NIX_OUTPUT=$(mktemp)",
        "  timeout 300 nix-portable nix-shell $NIX_SHELL_PACKAGES --run 'python -c \"$PYTHON_CODE\"' 2>&1 | tee \"$TEMP_NIX_OUTPUT\"",
        "  NIX_EXIT=${PIPESTATUS[0]}",
        "  NIX_OUTPUT=$(cat \"$TEMP_NIX_OUTPUT\" 2>/dev/null || echo \"\")",
        "  rm -f \"$TEMP_NIX_OUTPUT\"",
        "  set -e",
        "  ",
        "  # Output was already streamed above via tee, but show summary",
        "  echo \"=== end of nix-shell output ===\"",
        "  ",
        "  if [ $NIX_EXIT -ne 0 ]; then",
        "    echo \"nix-shell failed with exit code $NIX_EXIT\"",
        "    ",
        "    # Check for common package name errors",
        "    if echo \"$NIX_OUTPUT\" | grep -q \"undefined variable\"; then",
        "      MISSING_PKG=$(echo \"$NIX_OUTPUT\" | grep -o \"undefined variable '[^']*'\" | sed \"s/undefined variable '//\" | sed \"s/'//\" || echo \"unknown\")",
        "      echo \"Error: Package '$MISSING_PKG' not found in nixpkgs\"",
        "      echo \"Common fixes:\"",
        "      echo \"  - 'make' should be 'gnumake' (or is included with gcc/stdenv)\"",
        "      echo \"  - Check package name at: https://search.nixos.org/packages\"",
        "      echo \"  - Some packages may need different names (e.g., 'python3' vs 'python311')\"",
        "    fi",
        "    ",
        "    # Check if the error is specifically about downloading",
        "    if echo \"$NIX_OUTPUT\" | grep -q \"unable to build packages\"; then",
        "      echo \"Error: nix-portable cannot download/build packages\"",
        "      echo \"This usually means:\"",
        "      echo \"  1. Network connectivity issues (check if pods can reach internet)\"",
        "      echo \"  2. nix-portable configuration problems\"",
        "      echo \"  3. Missing database (which we're trying to create)\"",
        "      echo \"\"",
        "      echo \"SOLUTION: Ensure Argo workflow pods have network access to:\"",
        "      echo \"  - cache.nixos.org (for downloading packages)\"",
        "      echo \"  - github.com (for evaluating nixpkgs)\"",
        "      echo \"\"",
        "      echo \"Once network access is available, nix-portable will:\"",
        "      echo \"  1. Download packages (if needed)\"",
        "      echo \"  2. Create database\"",
        "      echo \"  3. Persist database to shared store via symlink\"",
        "      echo \"  4. Use cached packages on subsequent runs\"",
        "    fi",
        "    ",
        "    echo \"Checking if database was created...\"",
        "    if [ -f ~/.nix-portable/nix/var/nix/db/db.sqlite ]; then",
        "      DB_SIZE=$(stat -c%s ~/.nix-portable/nix/var/nix/db/db.sqlite 2>/dev/null || echo 0)",
        "      echo \"Database was created (size: $DB_SIZE bytes) - packages may have been registered\"",
        "      echo \"Even though nix-shell failed, database exists - next run should work\"",
        "    else",
        "      echo \"Database was not created\"",
        "      echo \"This confirms nix-portable cannot download packages (network/configuration issue)\"",
        "    fi",
        "    exit $NIX_EXIT",
        "  fi",
        "  ",
        "  # No syncing needed - PVC is mounted directly to ~/.nix-portable/nix/store",
        "  # Packages and database are written directly to the PVC, automatically shared across containers",
        "  if [ -d ~/.nix-portable/nix/store ]; then",
        "    PACKAGE_COUNT=$(find ~/.nix-portable/nix/store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || echo 0)",
        "    echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Packages in shared store: $PACKAGE_COUNT (written directly to PVC, no sync needed)\"",
        "    if [ -f ~/.nix-portable/nix/store/.nix-db/db.sqlite ]; then",
        "      DB_SIZE=$(stat -c%s ~/.nix-portable/nix/store/.nix-db/db.sqlite 2>/dev/null || echo 0)",
        "      echo -e \"\\033[0;34m[NIX CACHE]\\033[0m Database in shared store (size: $DB_SIZE bytes, written directly to PVC)\"",
        "    fi",
        "  fi",
        "else",
        "  python -c \"$PYTHON_CODE\"",
        "fi",
    ])
    
    return "\n".join(script_parts)


def create_workflow_with_hera(
    python_code: str,
    dependencies: Optional[str] = None,
    requirements_file: Optional[str] = None,
    system_dependencies: Optional[str] = None,
    use_cache: bool = True,
    namespace: str = "argo"
) -> str:
    """
    Create an Argo Workflow using Hera SDK with hybrid UV/Nix support.
    
    This replaces ~270 lines of complex YAML template manipulation with clean,
    type-safe Python code.
    
    Args:
        python_code: Python code to execute
        dependencies: Space or comma-separated Python package names (optional)
        requirements_file: requirements.txt content (optional)
        system_dependencies: Space or comma-separated Nix package names (optional, e.g., "gcc make")
        use_cache: Whether to mount cache volumes (default: True)
        namespace: Kubernetes namespace for the workflow
        
    Returns:
        workflow_id: The generated workflow name/ID
        
    Raises:
        HTTPException: If workflow creation fails
    """
    # Validate PVCs exist
    core_api = CoreV1Api()
    required_pvcs = ["task-results-pvc"]
    if use_cache:
        required_pvcs.extend(["uv-cache-pvc", "nix-store-pvc"])
    
    for pvc_name in required_pvcs:
        try:
            pvc = core_api.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace
            )
            pvc_status = pvc.status.phase if pvc.status else "Unknown"
            if pvc_status != "Bound":
                raise HTTPException(
                    status_code=400,
                    detail=f"PVC '{pvc_name}' is not bound. Current status: {pvc_status}."
                )
        except Exception as pvc_error:
            if "404" in str(pvc_error) or "Not Found" in str(pvc_error):
                raise HTTPException(
                    status_code=400,
                    detail=f"PVC '{pvc_name}' not found. Please create it first using: kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml"
                )
            if isinstance(pvc_error, HTTPException):
                raise pvc_error
            print(f"Warning: Could not verify PVC '{pvc_name}' status: {pvc_error}")
    
    # Determine if we need dependencies handling
    has_dependencies = bool(dependencies or requirements_file or system_dependencies)
    
    # Build volumes list
    volumes = [
        Volume(
            name="task-results",
            persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="task-results-pvc")
        )
    ]
    
    # Add cache volumes if enabled
    if use_cache:
        volumes.extend([
            Volume(
                name="uv-cache",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="uv-cache-pvc")
            ),
            Volume(
                name="nix-store",
                persistent_volume_claim=PersistentVolumeClaimVolumeSource(claim_name="nix-store-pvc")
            )
        ])
    
    # Build volume mounts
    volume_mounts = [
        VolumeMount(name="task-results", mount_path="/mnt/results")
    ]
    
    if use_cache:
        volume_mounts.extend([
            VolumeMount(name="uv-cache", mount_path="/root/.cache/uv"),
            # Mount nix-store directly to nix-portable's expected location to avoid copying
            # This eliminates the need for rsync/cp - packages are directly accessible
            VolumeMount(name="nix-store", mount_path="/root/.nix-portable/nix/store"),
            # Create symlink for backward compatibility with scripts that reference /nix/store
            # Note: We'll create this symlink in the script since Kubernetes can't create symlinks during mount
        ])
    
    # Create workflow with Hera
    workflow = Workflow(
        generate_name="python-job-",
        entrypoint="main",
        namespace=namespace,
        volumes=volumes
    )
    
    # Build environment variables
    env_vars = [
        EnvVar(name="ARGO_WORKFLOW_NAME", value="{{workflow.name}}"),
        EnvVar(name="PYTHON_CODE", value=python_code),
    ]
    
    # Determine base image
    # Use nix-portable base if system dependencies are needed, otherwise use standard Python image
    if system_dependencies:
        base_image = os.getenv("NIX_PORTABLE_BASE_IMAGE", "nix-portable-base:latest")
        # Note: For kind clusters, use "nix-portable-base:latest" (loaded via kind load docker-image)
        # For production, use your registry: "your-registry/nix-portable-base:latest"
        env_vars.append(EnvVar(name="SYSTEM_DEPS", value=system_dependencies))
    else:
        base_image = "python:3.11-slim"
    
    if has_dependencies:
        # Use script template for dependency management
        if dependencies:
            env_vars.append(EnvVar(name="PYTHON_DEPS", value=dependencies))
        elif requirements_file:
            env_vars.append(EnvVar(name="DEPENDENCIES", value="requirements.txt"))
        
        script_source = build_script_source(
            dependencies=dependencies,
            requirements_file=requirements_file,
            system_dependencies=system_dependencies,
            use_cache=use_cache
        )
        
        script_template = Script(
            name="main",
            image=base_image,
            image_pull_policy="IfNotPresent",  # Use local image in kind clusters
            command=["bash"],
            source=script_source,
            env=env_vars,
            volume_mounts=volume_mounts
        )
        
        workflow.templates.append(script_template)
    else:
        # Use container template for simple execution (no dependencies)
        container_template = Container(
            name="main",
            image=base_image,
            image_pull_policy="IfNotPresent",  # Use local image in kind clusters
            command=["python", "-c"],
            args=[python_code],
            env=env_vars,
            volume_mounts=volume_mounts
        )
        
        workflow.templates.append(container_template)
    
    # Create the workflow using Kubernetes API directly
    # Hera SDK's create() requires Argo server host, so we build the workflow dict
    # and submit it via Kubernetes API (same as current implementation)
    try:
        # Build workflow object using Hera SDK (handles all serialization)
        workflow_obj = workflow.build()
        
        # Convert Workflow object to dict for Kubernetes API
        # Hera SDK 5.26+ uses Pydantic v2, so we use model_dump()
        if isinstance(workflow_obj, dict):
            # Already a dict
            workflow_dict = workflow_obj
        elif hasattr(workflow_obj, 'model_dump'):
            # Pydantic v2 - convert to dict with proper serialization
            workflow_dict = workflow_obj.model_dump(exclude_none=True, by_alias=True, mode='json')
        elif hasattr(workflow_obj, 'model_dump_json'):
            # Pydantic v2 - convert via JSON string
            import json
            workflow_dict = json.loads(workflow_obj.model_dump_json(exclude_none=True, by_alias=True))
        elif hasattr(workflow_obj, 'dict'):
            # Pydantic v1 - convert to dict
            workflow_dict = workflow_obj.dict(exclude_none=True, by_alias=True)
        else:
            # Fallback: try to convert using json
            import json
            try:
                workflow_dict = json.loads(json.dumps(workflow_obj, default=str))
            except Exception:
                # Last resort: convert to dict manually
                workflow_dict = dict(workflow_obj) if hasattr(workflow_obj, '__dict__') else {}
        
        # Submit workflow via Kubernetes CustomObjectsApi
        api_instance = CustomObjectsApi()
        result = api_instance.create_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace=namespace,
            plural="workflows",
            body=workflow_dict
        )
        
        # Extract workflow ID from result
        workflow_id = result.get("metadata", {}).get("name", "unknown")
        
        if not workflow_id or workflow_id == "unknown":
            raise HTTPException(
                status_code=500,
                detail="Failed to extract workflow ID from created workflow"
            )
        return str(workflow_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create workflow: {str(e)}"
        )
