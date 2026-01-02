# Bunnyshell CLI Deployment Guide

This guide shows you how to deploy the Argo Workflow Manager using the Bunnyshell CLI (`bns`) instead of the web UI.

## Prerequisites

- Bunnyshell account
- Kubernetes cluster connected to Bunnyshell
- Git repository connected to Bunnyshell
- Argo Workflows installed in your cluster (see `DEPLOYMENT_STRATEGY.md` Phase 2)
- Kubernetes resources set up (see `DEPLOYMENT_STRATEGY.md` Phase 3)

## Installation

### Install Bunnyshell CLI

**macOS:**
```bash
brew install bunnyshell/tap/bns
```

**Linux:**
```bash
curl -fsSL https://cli.bunnyshell.com/install.sh | bash
```

**Windows:**
```powershell
# Using Chocolatey
choco install bns

# Or download from: https://cli.bunnyshell.com/
```

**Verify Installation:**
```bash
bns --version
```

### Authenticate CLI

1. Get your API key from Bunnyshell:
   - Log in to [Bunnyshell Dashboard](https://dashboard.bunnyshell.com)
   - Go to **Settings** → **API Keys**
   - Create a new API key or use an existing one

2. Configure the CLI:
   ```bash
   bns configure
   ```
   
   This will prompt you for:
   - API Key: Your Bunnyshell API key
   - Organization: Your organization name/ID
   - Project: Your project name/ID (optional)

   Or set environment variables:
   ```bash
   export BUNNYSHELL_API_KEY="your-api-key"
   export BUNNYSHELL_ORGANIZATION="your-org-id"
   export BUNNYSHELL_PROJECT="your-project-id"  # Optional
   ```

3. Verify authentication:
   ```bash
   bns organizations list
   ```

## Deployment Methods

### Method 1: Create Environment from Configuration File (Recommended)

This method creates a new environment from your `bunnyshell.yaml` file.

#### Step 1: Ensure Prerequisites

```bash
# Set up Kubernetes resources (if not already done)
./scripts/setup-k8s-resources.sh
```

#### Step 2: List Available Clusters and Repositories

```bash
# List clusters
bns clusters list

# List repositories
bns repositories list
```

Note the IDs of your cluster and repository for the next step.

#### Step 3: Create Environment from bunnyshell.yaml

```bash
bns environments create \
  --name argo-workflow-manager \
  --cluster-id <cluster-id> \
  --repository-id <repository-id> \
  --branch main \
  --config-file bunnyshell.yaml
```

**Parameters:**
- `--name`: Environment name (e.g., `argo-workflow-manager`)
- `--cluster-id`: Your Kubernetes cluster ID (from `bns clusters list`)
- `--repository-id`: Your Git repository ID (from `bns repositories list`)
- `--branch`: Git branch containing `bunnyshell.yaml` (e.g., `main`, `master`)
- `--config-file`: Path to `bunnyshell.yaml` (default: `bunnyshell.yaml`)

**Example:**
```bash
bns environments create \
  --name argo-workflow-manager \
  --cluster-id cl_abc123xyz \
  --repository-id repo_def456uvw \
  --branch main \
  --config-file bunnyshell.yaml
```

This will:
- Create the environment
- Build Docker images for backend and frontend
- Deploy all components to your cluster
- Return an environment ID

#### Step 4: Deploy the Environment

After creating the environment, deploy it:

```bash
# Get the environment ID from the previous command output
ENV_ID="<environment-id>"

# Deploy the environment
bns environments deploy --id $ENV_ID
```

Or combine create and deploy:
```bash
ENV_ID=$(bns environments create \
  --name argo-workflow-manager \
  --cluster-id <cluster-id> \
  --repository-id <repository-id> \
  --branch main \
  --config-file bunnyshell.yaml \
  --output json | jq -r '.id')

bns environments deploy --id $ENV_ID
```

#### Step 5: Monitor Deployment

```bash
# Watch deployment events
bns events list --environment-id $ENV_ID

# Get detailed event information
bns events show --id <event-id>

# Check environment status
bns environments show --id $ENV_ID
```

#### Step 6: Configure ServiceAccount

After deployment completes, configure the ServiceAccount:

```bash
# Auto-detect namespace and configure
./scripts/configure-serviceaccount.sh

# Or specify namespace manually
./scripts/configure-serviceaccount.sh <namespace>
```

---

### Method 2: Deploy Existing Environment

If you've already created an environment via UI or CLI:

```bash
# List environments
bns environments list

# Deploy specific environment
bns environments deploy --id <environment-id>

# Or by name (if unique)
bns environments deploy --name argo-workflow-manager
```

---

### Method 3: Update and Redeploy

To update an existing environment:

```bash
# Update environment configuration
bns environments update \
  --id <environment-id> \
  --config-file bunnyshell.yaml

# Redeploy
bns environments deploy --id <environment-id>
```

---

## Useful CLI Commands

### Environment Management

```bash
# List all environments
bns environments list

# Show environment details
bns environments show --id <environment-id>

# Show environment by name
bns environments show --name argo-workflow-manager

# Delete environment
bns environments delete --id <environment-id>
```

### Component Management

```bash
# List components in an environment
bns components list --environment-id <environment-id>

# Show component details
bns components show --id <component-id>

# Restart a component
bns components restart --id <component-id>

# View component logs
bns components logs --id <component-id> --follow
```

### Event Monitoring

```bash
# List recent events
bns events list

# List events for an environment
bns events list --environment-id <environment-id>

# Show event details
bns events show --id <event-id>

# Watch events in real-time
bns events list --environment-id <environment-id> --watch
```

### Cluster and Repository Management

```bash
# List clusters
bns clusters list

# Show cluster details
bns clusters show --id <cluster-id>

# List repositories
bns repositories list

# Show repository details
bns repositories show --id <repository-id>
```

---

## Complete CLI Deployment Workflow

Here's a complete script for deploying from scratch using the CLI:

```bash
#!/bin/bash
set -e

# Configuration
ENV_NAME="argo-workflow-manager"
BRANCH="main"
CONFIG_FILE="bunnyshell.yaml"

# Step 1: Set up Kubernetes resources
echo "Setting up Kubernetes resources..."
./scripts/setup-k8s-resources.sh

# Step 2: Get cluster and repository IDs
echo "Fetching cluster and repository information..."
CLUSTER_ID=$(bns clusters list --output json | jq -r '.[0].id')
REPO_ID=$(bns repositories list --output json | jq -r '.[0].id')

echo "Cluster ID: $CLUSTER_ID"
echo "Repository ID: $REPO_ID"

# Step 3: Create environment
echo "Creating environment..."
ENV_ID=$(bns environments create \
  --name "$ENV_NAME" \
  --cluster-id "$CLUSTER_ID" \
  --repository-id "$REPO_ID" \
  --branch "$BRANCH" \
  --config-file "$CONFIG_FILE" \
  --output json | jq -r '.id')

echo "Environment ID: $ENV_ID"

# Step 4: Deploy environment
echo "Deploying environment..."
DEPLOY_EVENT=$(bns environments deploy --id "$ENV_ID" --output json | jq -r '.id')
echo "Deployment event ID: $DEPLOY_EVENT"

# Step 5: Monitor deployment
echo "Monitoring deployment..."
bns events show --id "$DEPLOY_EVENT" --watch

# Step 6: Get namespace
echo "Finding Bunnyshell namespace..."
NS=$(kubectl get namespaces -o name | grep -i argo-workflow-manager | sed 's/namespace\///' | head -n 1)

# Step 7: Configure ServiceAccount
if [ -n "$NS" ]; then
  echo "Configuring ServiceAccount in namespace: $NS"
  ./scripts/configure-serviceaccount.sh "$NS"
else
  echo "Warning: Could not auto-detect namespace. Please run:"
  echo "  ./scripts/configure-serviceaccount.sh <namespace>"
fi

echo "Deployment complete!"
echo "Environment ID: $ENV_ID"
```

Save this as `deploy.sh`, make it executable, and run:
```bash
chmod +x deploy.sh
./deploy.sh
```

---

## Troubleshooting

### Authentication Issues

```bash
# Re-authenticate
bns configure

# Check current configuration
bns organizations list
```

### Environment Creation Fails

```bash
# Check cluster status
bns clusters show --id <cluster-id>

# Check repository access
bns repositories show --id <repository-id>

# Verify bunnyshell.yaml syntax
# (Bunnyshell CLI will validate on create)
```

### Deployment Fails

```bash
# Check event details
bns events show --id <event-id>

# Check component status
bns components list --environment-id <environment-id>

# View component logs
bns components logs --id <component-id>
```

### Finding Environment Namespace

```bash
# List all namespaces
kubectl get namespaces

# Or use the environment name pattern
kubectl get namespaces | grep argo-workflow-manager
```

---

## Integration with CI/CD

You can integrate Bunnyshell CLI into your CI/CD pipeline:

### GitHub Actions Example

```yaml
name: Deploy to Bunnyshell

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install Bunnyshell CLI
        run: |
          curl -fsSL https://cli.bunnyshell.com/install.sh | bash
      
      - name: Configure Bunnyshell CLI
        env:
          BUNNYSHELL_API_KEY: ${{ secrets.BUNNYSHELL_API_KEY }}
          BUNNYSHELL_ORGANIZATION: ${{ secrets.BUNNYSHELL_ORG_ID }}
        run: |
          bns configure --api-key "$BUNNYSHELL_API_KEY" --organization "$BUNNYSHELL_ORGANIZATION"
      
      - name: Deploy Environment
        run: |
          ENV_ID=$(bns environments deploy --name argo-workflow-manager --output json | jq -r '.id')
          echo "Deployed environment: $ENV_ID"
```

### GitLab CI Example

```yaml
deploy:
  stage: deploy
  image: alpine:latest
  before_script:
    - apk add --no-cache curl jq
    - curl -fsSL https://cli.bunnyshell.com/install.sh | sh
    - export PATH="$PATH:/usr/local/bin"
    - bns configure --api-key "$BUNNYSHELL_API_KEY" --organization "$BUNNYSHELL_ORG_ID"
  script:
    - bns environments deploy --name argo-workflow-manager
  only:
    - main
```

---

## Comparison: CLI vs UI

| Feature | CLI | UI |
|---------|-----|-----|
| Automation | ✅ Excellent | ❌ Manual |
| CI/CD Integration | ✅ Yes | ❌ No |
| Scripting | ✅ Yes | ❌ No |
| Monitoring | ✅ Commands available | ✅ Visual dashboard |
| Initial Setup | ⚠️ Requires API key | ✅ Easier |
| Learning Curve | ⚠️ Steeper | ✅ Easier |

**Recommendation**: Use CLI for automation and CI/CD, UI for initial setup and monitoring.

---

## Additional Resources

- [Bunnyshell CLI Documentation](https://documentation.bunnyshell.com/docs/bunnyshell-cli)
- [Bunnyshell CLI Installation](https://documentation.bunnyshell.com/docs/bunnyshell-cli-install)
- [Environment Actions](https://documentation.bunnyshell.com/docs/environment-actions)
- [API Reference](https://documentation.bunnyshell.com/reference)

---

## Next Steps

After deploying via CLI:

1. ✅ Configure ServiceAccount: `./scripts/configure-serviceaccount.sh`
2. ✅ Verify deployment: See `DEPLOYMENT_STRATEGY.md` Phase 6
3. ✅ Set up monitoring and alerting
4. ✅ Configure CI/CD pipeline (optional)

For detailed troubleshooting, see `DEPLOYMENT_STRATEGY.md`.

