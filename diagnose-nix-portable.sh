#!/bin/bash
# Diagnostic script to identify differences between macOS environments
# Run this on both machines and compare the output

echo "=========================================="
echo "Nix-Portable Environment Diagnostics"
echo "=========================================="
echo ""

echo "1. macOS Version:"
sw_vers
echo ""

echo "2. System Architecture:"
uname -m
arch
echo ""

echo "3. Docker Version:"
docker --version 2>/dev/null || echo "Docker not found"
docker info 2>/dev/null | grep -E "Operating System|Architecture|OSType|Kernel Version" || echo "Docker info not available"
echo ""

echo "4. Docker Desktop Settings (if applicable):"
if [ -f ~/Library/Group\ Containers/group.com.docker/settings.json ]; then
    echo "Docker Desktop settings file exists"
    cat ~/Library/Group\ Containers/group.com.docker/settings.json 2>/dev/null | grep -E "vmType|resources|security" || echo "Could not read settings"
else
    echo "Docker Desktop settings file not found"
fi
echo ""

echo "5. Kubernetes/Kind Version:"
kubectl version --client 2>/dev/null | head -1 || echo "kubectl not found"
kind version 2>/dev/null || echo "kind not found"
echo ""

echo "6. Kind Cluster Info (if running):"
kind get clusters 2>/dev/null || echo "No kind clusters found"
if kind get clusters 2>/dev/null | grep -q .; then
    CLUSTER=$(kind get clusters | head -1)
    echo "Cluster: $CLUSTER"
    kubectl get nodes -o wide 2>/dev/null || echo "Cannot get nodes"
    kubectl describe node 2>/dev/null | grep -E "OS Image|Architecture|Operating System" | head -3 || echo "Cannot describe nodes"
fi
echo ""

echo "7. Container Runtime Info:"
docker info 2>/dev/null | grep -E "Runtime|Default Runtime" || echo "Runtime info not available"
echo ""

echo "8. File System Type (for Docker volumes):"
df -T / 2>/dev/null || df -h / | head -1
echo ""

echo "9. Security Settings:"
echo "SIP Status:"
csrutil status 2>/dev/null || echo "Cannot check SIP status (may need sudo)"
echo ""

echo "10. Docker Container Test (nix-portable binary):"
if docker ps &>/dev/null; then
    echo "Testing nix-portable in a container..."
    docker run --rm python:3.11-slim sh -c "
        apt-get update -qq && apt-get install -y -qq curl >/dev/null 2>&1 && \
        curl -L https://github.com/DavHau/nix-portable/releases/latest/download/nix-portable-x86_64 \
        -o /tmp/nix-portable && chmod +x /tmp/nix-portable && \
        /tmp/nix-portable nix --version 2>&1
    " 2>&1 || echo "Failed to test nix-portable in container"
else
    echo "Docker not running or not accessible"
fi
echo ""

echo "11. Environment Variables:"
echo "PATH: $PATH"
echo "HOME: $HOME"
echo "USER: $USER"
echo ""

echo "12. Resource Limits (if in container):"
if [ -f /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
    echo "Memory limit: $(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)"
fi
if [ -f /sys/fs/cgroup/cpu/cpu.cfs_quota_us ]; then
    echo "CPU quota: $(cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us)"
fi
echo ""

echo "13. Network Connectivity Test:"
curl -s --max-time 5 https://cache.nixos.org >/dev/null 2>&1 && echo "✓ Can reach cache.nixos.org" || echo "✗ Cannot reach cache.nixos.org"
curl -s --max-time 5 https://github.com >/dev/null 2>&1 && echo "✓ Can reach github.com" || echo "✗ Cannot reach github.com"
echo ""

echo "=========================================="
echo "Diagnostics Complete"
echo "=========================================="
echo ""
echo "Compare the output from both machines, especially:"
echo "- macOS version differences"
echo "- Docker version differences"
echo "- Architecture (Intel vs Apple Silicon)"
echo "- Container runtime settings"
echo "- Security settings (SIP)"
echo "- Docker Desktop configuration"
