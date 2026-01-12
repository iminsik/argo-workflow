.PHONY: cluster-up cluster-down dev-up dev-down argo-list argo-logs cache-setup build-nix-image load-nix-image

cluster-up:
	@echo "Creating host directories for persistent volumes..."
	@mkdir -p /tmp/argo-nix-store /tmp/argo-uv-cache /tmp/argo-task-results
	@chmod 777 /tmp/argo-nix-store /tmp/argo-uv-cache /tmp/argo-task-results
	@echo "Creating Kind cluster..."
	kind create cluster --name argo-dev --config infrastructure/k8s/kind-config.yaml
	kubectl create namespace argo || true
	kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
	kubectl apply -f infrastructure/k8s/rbac.yaml
	kubectl apply -f infrastructure/k8s/pv.yaml
	kubectl apply -f infrastructure/k8s/pv-cache-volumes.yaml
	kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml
	@echo "Building and loading nix-portable-base image..."
	@$(MAKE) build-nix-image load-nix-image

cluster-down:
	kind delete cluster --name argo-dev

dev-up:
	docker-compose up --build

dev-down:
	docker-compose down -v

argo-list: ## List all running workflows in Kind
	argo list

argo-logs: ## View logs of latest workflow (usage: make argo-logs name=my-wf)
	argo logs -f $(name)

argo-watch: ## Watch workflow progress
	argo watch $(name)

cache-setup: ## Create cache PVCs for UV and Nix (required for dependency caching)
	kubectl apply -f infrastructure/k8s/pv-cache-volumes.yaml
	kubectl apply -f infrastructure/k8s/pvc-cache-volumes.yaml
	@echo "Cache PVCs created. Verify with: kubectl get pvc -n argo"

build-nix-image: ## Build the nix-portable-base Docker image
	@echo "Building nix-portable-base image..."
	cd infrastructure/argo && docker build -f Dockerfile.nix-portable-base -t nix-portable-base:latest .

load-nix-image: ## Load nix-portable-base image into kind cluster
	@echo "Loading nix-portable-base image into kind cluster..."
	kind load docker-image nix-portable-base:latest --name argo-dev || echo "Warning: Failed to load image. Make sure kind cluster is running."

clean-nix-store: ## Clean up nix-store (removes all packages and database)
	@echo "Cleaning nix-store..."
	@docker exec argo-dev-control-plane sh -c "rm -rf /tmp/argo-nix-store/* /tmp/argo-nix-store/.nix-db/* 2>/dev/null; echo 'Nix store cleaned. Packages and database removed.'" || echo "Warning: Could not clean nix-store. Make sure Kind cluster is running."

nix-store-info: ## Show nix-store disk usage and package count
	@echo "Nix Store Information:"
	@docker exec argo-dev-control-plane sh -c "echo 'Total size:'; du -sh /tmp/argo-nix-store 2>/dev/null; echo 'Package count:'; find /tmp/argo-nix-store -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l; echo 'Database size:'; du -sh /tmp/argo-nix-store/.nix-db/db.sqlite 2>/dev/null || echo 'No database'; echo 'Disk usage:'; df -h /tmp/argo-nix-store 2>/dev/null | tail -1" || echo "Warning: Could not get nix-store info. Make sure Kind cluster is running."
