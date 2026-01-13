#!/bin/bash
# Pre-flight checks before setting up the cluster
# Ensures all requirements are met

set -e

echo "=========================================="
echo "Pre-flight Checks"
echo "=========================================="
echo ""

ERRORS=0
WARNINGS=0

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version 2>/dev/null || echo "unknown")
    echo "   ✅ Docker found: $DOCKER_VERSION"
    
    # Check if Docker is running
    if docker info &>/dev/null; then
        echo "   ✅ Docker is running"
    else
        echo "   ❌ Docker is not running"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ❌ Docker not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check kind
echo "2. Checking kind..."
if command -v kind &> /dev/null; then
    KIND_VERSION=$(kind version 2>/dev/null | head -1 || echo "unknown")
    echo "   ✅ kind found: $KIND_VERSION"
    
    # Check if kind version is recent enough (v0.31.0+ recommended)
    KIND_VERSION_NUM=$(kind version 2>/dev/null | grep -oP 'v\K[0-9]+\.[0-9]+' | head -1 || echo "0.0")
    KIND_MAJOR=$(echo "$KIND_VERSION_NUM" | cut -d. -f1)
    KIND_MINOR=$(echo "$KIND_VERSION_NUM" | cut -d. -f2)
    
    if [ "$KIND_MAJOR" -gt 0 ] || ([ "$KIND_MAJOR" -eq 0 ] && [ "$KIND_MINOR" -ge 31 ]); then
        echo "   ✅ kind version is recent (>=v0.31.0 recommended)"
    else
        echo "   ⚠️  kind version may be too old (v0.31.0+ recommended for containerd 2.x)"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    echo "   ❌ kind not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check kubectl
echo "3. Checking kubectl..."
if command -v kubectl &> /dev/null; then
    KUBECTL_VERSION=$(kubectl version --client 2>/dev/null | grep -oP 'GitVersion:\"v\K[^\"]+' | head -1 || echo "unknown")
    echo "   ✅ kubectl found: v$KUBECTL_VERSION"
else
    echo "   ❌ kubectl not found"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Check if cluster already exists
echo "4. Checking for existing cluster..."
CLUSTER_NAME="argo-dev"
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "   ⚠️  Cluster '${CLUSTER_NAME}' already exists"
    echo "   Checking containerd version in existing cluster..."
    
    if command -v kubectl &> /dev/null; then
        CONTAINERD_VERSION=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}' 2>/dev/null || echo "")
        if [ -n "$CONTAINERD_VERSION" ]; then
            VERSION_NUM=$(echo "$CONTAINERD_VERSION" | sed 's/containerd:\/\///')
            MAJOR_VERSION=$(echo "$VERSION_NUM" | cut -d. -f1)
            
            if [ "$MAJOR_VERSION" -ge 2 ] 2>/dev/null; then
                echo "   ✅ Containerd version $VERSION_NUM meets requirement (>=2.0.0)"
            else
                echo "   ❌ Containerd version $VERSION_NUM is too old (requires >=2.0.0)"
                echo "      Please delete and recreate the cluster:"
                echo "        kind delete cluster --name ${CLUSTER_NAME}"
                echo "        make cluster-up"
                ERRORS=$((ERRORS + 1))
            fi
        else
            echo "   ⚠️  Could not determine containerd version"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
else
    echo "   ✅ No existing cluster found (will create new one)"
fi
echo ""

# Summary
echo "=========================================="
echo "Summary"
echo "=========================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ All checks passed! You're ready to create the cluster."
    echo ""
    echo "Run: make cluster-up"
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "⚠️  $WARNINGS warning(s) found, but no errors."
    echo "You can proceed, but consider addressing the warnings."
    echo ""
    echo "Run: make cluster-up"
    exit 0
else
    echo "❌ $ERRORS error(s) and $WARNINGS warning(s) found."
    echo "Please fix the errors before creating the cluster."
    exit 1
fi
