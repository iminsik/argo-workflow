.PHONY: cluster-up cluster-down dev-up dev-down argo-list argo-logs

cluster-up:
	kind create cluster --name argo-dev --config infrastructure/k8s/kind-config.yaml
	kubectl create namespace argo || true
	kubectl apply -n argo -f https://github.com/argoproj/argo-workflows/releases/download/v3.5.0/quick-start-minimal.yaml
	kubectl apply -f infrastructure/k8s/rbac.yaml

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
