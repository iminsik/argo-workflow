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

**Prerequisites:**
- A Bunnyshell account
- A Kubernetes cluster connected to Bunnyshell
- Git repository connected to Bunnyshell

**Deployment Steps:**
1. Connect your repository to Bunnyshell
2. Ensure your Kubernetes cluster is connected
3. Deploy the environment using the `bunnyshell.yaml` configuration
4. Configure environment variables as needed (especially `CORS_ORIGINS` for production)

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

[Add your license here]

