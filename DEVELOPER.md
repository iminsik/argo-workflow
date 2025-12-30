# Developer Guide

This guide is for developers working on the Argo Workflow Manager application.

## Prerequisites

- **Docker** and **Docker Compose** installed
- **Node.js** 20+ (for local frontend development, optional)
- **Python** 3.11+ (for local backend development, optional)
- **kubectl** configured to access a Kubernetes cluster
- **Kind** (for local Kubernetes cluster, optional)

## Local Development Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd argo-monorepo-old1
```

### 2. Set Up Kubernetes Cluster (if using Kind)

```bash
# Create a local Kind cluster with Argo Workflows
make cluster-up
```

This will:
- Create a Kind cluster named `argo-dev`
- Install Argo Workflows in the `argo` namespace
- Set up RBAC permissions

### 3. Start Development Environment

```bash
# Start all services (backend, frontend, postgres)
make dev-up
```

This will:
- Build and start the backend service on `http://localhost:8000`
- Build and start the frontend service on `http://localhost:5173`
- Start a PostgreSQL database

### 4. Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## Development Workflow

### Backend Development

The backend is a FastAPI application located in `apps/backend/`.

#### Structure

```
apps/backend/
├── app/
│   └── main.py          # FastAPI application
├── Dockerfile.dev       # Development Dockerfile
└── pyproject.toml       # Python dependencies
```

#### Key Features

- **CORS enabled** for frontend communication
- **Kubernetes API integration** for workflow management
- **Auto-reload** enabled in development mode

#### Running Locally (without Docker)

```bash
cd apps/backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install uv
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Environment Variables

- `WORKFLOW_MANIFEST_PATH`: Path to workflow YAML file (default: `/infrastructure/argo/python-processor.yaml`)
- `ARGO_NAMESPACE`: Kubernetes namespace for workflows (default: `argo`)

### Frontend Development

The frontend is a React + TypeScript application located in `apps/frontend/`.

#### Structure

```
apps/frontend/
├── src/
│   ├── App.tsx          # Main application component
│   └── main.tsx         # Entry point
├── Dockerfile.dev       # Development Dockerfile
├── package.json         # Node dependencies
└── vite.config.ts      # Vite configuration
```

#### Running Locally (without Docker)

```bash
cd apps/frontend
npm install
npm run dev
```

#### Environment Variables

- `VITE_API_URL`: Backend API URL (default: `http://localhost:8000`)

## Architecture

### Backend Architecture

```
┌─────────────┐
│   Frontend  │
│  (React)    │
└──────┬──────┘
       │ HTTP/REST
       ▼
┌─────────────┐
│   Backend   │
│  (FastAPI)  │
└──────┬──────┘
       │ Kubernetes API
       ▼
┌─────────────┐
│ Kubernetes  │
│   Cluster   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Argo      │
│ Workflows   │
└─────────────┘
```

### API Endpoints

- `POST /api/v1/tasks/submit` - Submit a new workflow
- `GET /api/v1/tasks` - List all workflows
- `POST /api/v1/tasks/callback` - Webhook callback endpoint

## Common Development Tasks

### Adding a New Workflow Template

1. Create a new YAML file in `infrastructure/argo/`
2. Update the backend to use the new template (or make it configurable)

### Debugging

#### Backend Logs

```bash
docker-compose logs -f backend
```

#### Frontend Logs

```bash
docker-compose logs -f frontend
```

#### Kubernetes/Argo Logs

```bash
# Workflow controller logs
kubectl logs -n argo -l app=workflow-controller -f

# View workflow status
kubectl get workflows -n argo

# View workflow details
kubectl describe workflow <workflow-name> -n argo
```

### Testing

#### Manual Testing

1. Start the development environment: `make dev-up`
2. Open http://localhost:5173
3. Click "Run Python Task" to submit a workflow
4. Check the task list to see workflow status

#### Testing Workflow Creation

```bash
# Submit a workflow via API
curl -X POST http://localhost:8000/api/v1/tasks/submit

# List workflows
curl http://localhost:8000/api/v1/tasks
```

## Troubleshooting

### Workflows Not Processing

If workflows stay in "Pending" status:

1. **Check namespace**: Workflows must be in the `argo` namespace (workflow controller runs in `--namespaced` mode)
2. **Check workflow controller**: `kubectl get pods -n argo | grep workflow-controller`
3. **Check logs**: `kubectl logs -n argo -l app=workflow-controller`

### CORS Errors

- Ensure backend CORS middleware is configured correctly
- Check that frontend is using the correct API URL
- Verify backend is running and accessible

### Kubernetes Connection Issues

If backend can't connect to Kubernetes:

1. **Check kubeconfig**: Ensure `~/.kube/config` is mounted in docker-compose
2. **Check network**: Backend uses `host.docker.internal` to reach host's Kubernetes API
3. **SSL verification**: Disabled for development (kind uses self-signed certs)

### Port Conflicts

If ports 8000 or 5173 are already in use:

1. Stop conflicting services
2. Or modify `docker-compose.yaml` to use different ports

## Code Style

### Python (Backend)

- Follow PEP 8
- Use type hints where possible
- Use FastAPI best practices

### TypeScript (Frontend)

- Use TypeScript strict mode
- Follow React best practices
- Use functional components with hooks

## Contributing

1. Create a feature branch
2. Make your changes
3. Test locally
4. Submit a pull request

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Argo Workflows Documentation](https://argoproj.github.io/argo-workflows/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)

