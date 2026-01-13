#!/bin/bash
# Check containerd version and ensure it meets requirements
# Required version: >2.0.0 (for nix-portable compatibility)

set -e

REQUIRED_VERSION="2.0.0"
CLUSTER_NAME="${1:-argo-dev}"

echo "=========================================="
echo "Containerd Version Check"
echo "=========================================="
echo ""

# Function to compare version numbers
# Returns 0 if version1 >= version2, 1 otherwise
version_compare() {
    local version1=$1
    local version2=$2
    
    # Remove "containerd://" prefix if present
    version1=$(echo "$version1" | sed 's/containerd:\/\///')
    version2=$(echo "$version2" | sed 's/containerd:\/\///')
    
    # Compare using sort -V (version sort)
    if printf '%s\n%s\n' "$version1" "$version2" | sort -V -C; then
        return 0  # version1 >= version2
    else
        return 1  # version1 < version2
    fi
}

# Check if kind cluster exists
if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    echo "❌ Error: Kind cluster '${CLUSTER_NAME}' not found"
    echo ""
    echo "Please create the cluster first:"
    echo "  make cluster-up"
    echo ""
    exit 1
fi

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ Error: kubectl not found"
    echo "Please install kubectl first"
    exit 1
fi

# Get containerd version from the cluster
echo "Checking containerd version in cluster '${CLUSTER_NAME}'..."
CONTAINERD_VERSION=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}' 2>/dev/null || echo "")

if [ -z "$CONTAINERD_VERSION" ]; then
    echo "❌ Error: Could not retrieve containerd version from cluster"
    echo "Make sure the cluster is running and accessible"
    exit 1
fi

# Extract version number (remove "containerd://" prefix)
VERSION_NUMBER=$(echo "$CONTAINERD_VERSION" | sed 's/containerd:\/\///')

echo "Current version: $CONTAINERD_VERSION"
echo "Required version: >$REQUIRED_VERSION"
echo ""

# Compare versions
if version_compare "$VERSION_NUMBER" "$REQUIRED_VERSION"; then
    echo "✅ Containerd version $VERSION_NUMBER meets requirement (>$REQUIRED_VERSION)"
    echo ""
    echo "Your cluster is compatible with nix-portable!"
    exit 0
else
    echo "❌ Containerd version $VERSION_NUMBER does NOT meet requirement (>$REQUIRED_VERSION)"
    echo ""
    echo "This version may cause issues with nix-portable."
    echo ""
    echo "To fix this:"
    echo "1. Upgrade kind to latest version:"
    echo "   brew upgrade kind"
    echo ""
    echo "2. Delete and recreate the cluster:"
    echo "   kind delete cluster --name ${CLUSTER_NAME}"
    echo "   make cluster-up"
    echo ""
    echo "3. Verify the new version:"
    echo "   ./scripts/check-containerd-version.sh"
    echo ""
    exit 1
fi
