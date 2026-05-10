#!/bin/bash
# =============================================================================
# Deploy Fraud Intelligence Platform to Local Kubernetes
# Requires: kubectl, Docker Desktop with Kubernetes enabled
# =============================================================================
set -e

NAMESPACE="fraud-platform"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
K8S_DIR="$SCRIPT_DIR/../kubernetes"
HELM_DIR="$SCRIPT_DIR/../helm/fraud-platform"

echo "============================================"
echo " Deploying Fraud Intelligence Platform"
echo " Target: Local Kubernetes (Docker Desktop)"
echo "============================================"
echo ""

# Check prerequisites
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found. Install it first."; exit 1; }

# Check if Kubernetes is running
kubectl cluster-info >/dev/null 2>&1 || { echo "Kubernetes cluster not reachable. Enable it in Docker Desktop."; exit 1; }

echo "==> Creating namespace..."
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# Check if Helm is available
if command -v helm >/dev/null 2>&1; then
    echo "==> Deploying with Helm..."
    helm upgrade --install fraud-platform "$HELM_DIR" \
        --namespace "$NAMESPACE" \
        --values "$HELM_DIR/values-local.yaml" \
        --wait \
        --timeout 5m
else
    echo "==> Helm not found. Deploying with kustomize..."
    kubectl apply -k "$K8S_DIR"
fi

echo ""
echo "==> Waiting for pods to be ready..."
kubectl wait --namespace "$NAMESPACE" \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/part-of=fraud-intelligence-platform \
    --timeout=300s 2>/dev/null || echo "Some pods may still be starting up."

echo ""
echo "==> Current pod status:"
kubectl get pods -n "$NAMESPACE"

echo ""
echo "============================================"
echo " Deployment complete!"
echo ""
echo " Access URLs (via port-forward):"
echo "   Frontend:    kubectl port-forward -n $NAMESPACE svc/frontend 3000:80"
echo "   Backend:     kubectl port-forward -n $NAMESPACE svc/backend 8000:8000"
echo "   Grafana:     kubectl port-forward -n $NAMESPACE svc/grafana 3001:3000"
echo "   Spark UI:    kubectl port-forward -n $NAMESPACE svc/spark-master 8080:8080"
echo "   MinIO:       kubectl port-forward -n $NAMESPACE svc/minio 9001:9001"
echo "============================================"
