.PHONY: cluster-up cluster-down dev-up dev-down argo-list argo-logs cache-setup build-nix-image load-nix-image

cluster-up:
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
