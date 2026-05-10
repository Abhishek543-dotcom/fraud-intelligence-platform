#!/bin/bash
# =============================================================================
# Teardown Fraud Intelligence Platform from Kubernetes
# =============================================================================
set -e

NAMESPACE="fraud-platform"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HELM_DIR="$SCRIPT_DIR/../helm/fraud-platform"

echo "============================================"
echo " Tearing Down Fraud Intelligence Platform"
echo "============================================"

if command -v helm >/dev/null 2>&1 && helm list -n "$NAMESPACE" | grep -q fraud-platform; then
    echo "==> Uninstalling Helm release..."
    helm uninstall fraud-platform -n "$NAMESPACE"
else
    echo "==> Deleting Kubernetes resources..."
    kubectl delete -k "$SCRIPT_DIR/../kubernetes" 2>/dev/null || true
fi

echo "==> Deleting PVCs..."
kubectl delete pvc --all -n "$NAMESPACE" 2>/dev/null || true

echo "==> Deleting namespace..."
kubectl delete namespace "$NAMESPACE" 2>/dev/null || true

echo ""
echo "============================================"
echo " Teardown complete."
echo "============================================"
