# Argo Workflow Manager

A full-stack application for managing and monitoring Argo Workflows with a modern web interface.

## Overview

This monorepo contains:
- **Frontend**: React + TypeScript + Vite web application
- **Backend**: FastAPI Python service for workflow management
- **Infrastructure**: Kubernetes/Argo Workflows configuration

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Kubernetes cluster (Kind recommended for local development)
- kubectl configured to access your cluster

### For Developers

See [DEVELOPER.md](./DEVELOPER.md) for detailed development setup and workflow.

### For DevOps

See [DEVOPS.md](./DEVOPS.md) for deployment and infrastructure management.

### Bunnyshell Deployment

This repository is configured for deployment on [Bunnyshell](https://bunnyshell.com). The `bunnyshell.yaml` file defines the environment configuration.

**Deployment Options:**
- **CLI Deployment**: See [BUNNYSHELL_CLI_DEPLOYMENT.md](./BUNNYSHELL_CLI_DEPLOYMENT.md) for command-line deployment
- **UI Deployment**: See [BUNNYSHELL_DEPLOYMENT.md](./BUNNYSHELL_DEPLOYMENT.md) for web UI deployment
- **Quick Start**: See [DEPLOYMENT_SUMMARY.md](./DEPLOYMENT_SUMMARY.md) for a quick overview

**Quick Overview:**
- Connect your Kubernetes cluster to Bunnyshell
- Connect your Git repository to Bunnyshell
- Create a new environment from the `bunnyshell.yaml` configuration
- Configure RBAC for Argo Workflows access
- Update `CORS_ORIGINS` for production use

**Prerequisites:**
- A Bunnyshell account
- A Kubernetes cluster connected to Bunnyshell
- Git repository connected to Bunnyshell

**Quick CLI Deployment:**
```bash
# 1. Set up Kubernetes resources
./scripts/setup-k8s-resources.sh

# 2. Deploy via CLI
bns environments create \
  --name argo-workflow-manager \
  --cluster-id <cluster-id> \
  --repository-id <repository-id> \
  --branch main \
  --config-file bunnyshell.yaml

bns environments deploy --id <environment-id>

# 3. Configure ServiceAccount
./scripts/configure-serviceaccount.sh
```

**Note:** Make sure to update the `CORS_ORIGINS` environment variable in the backend component to match your frontend URL in production.

### For End Users

See [USER.md](./USER.md) for how to use the application.

## Project Structure

```
.
├── apps/
│   ├── backend/          # FastAPI backend service
│   └── frontend/         # React frontend application
├── infrastructure/
│   ├── argo/            # Argo Workflow definitions
│   └── k8s/             # Kubernetes configuration
├── docker-compose.yaml   # Local development setup
└── Makefile             # Common commands
```

## Quick Commands

```bash
# Start local development environment
make dev-up

# Stop local development environment
make dev-down

# Set up Kubernetes cluster with Argo Workflows
make cluster-up

# Tear down Kubernetes cluster
make cluster-down
```

## License

MIT

