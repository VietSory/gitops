# Bootstrap secrets

This repository keeps credentials out of Git. Create the required Kubernetes Secrets before relying on the monitoring stack to become healthy.

For a fresh cluster, make sure the destination namespace exists first:

```bash
kubectl get namespace monitoring >/dev/null 2>&1 || kubectl create namespace monitoring
```

## Grafana administrator

Generate a strong password with your preferred secret manager or password generator, then create the Secret without committing the value:

```bash
kubectl -n monitoring create secret generic grafana-admin-credentials \
  --from-literal=admin-user=admin \
  --from-literal=admin-password='<strong-generated-password>'
```

The Helm values reference the Secret by name and expect the keys `admin-user` and `admin-password`.

## Alertmanager Gmail app password

Create the existing Alertmanager Secret the same way:

```bash
kubectl -n monitoring create secret generic alertmanager-gmail-secret \
  --from-literal=smtp-auth-password='<gmail-app-password>'
```

Do not add either Secret manifest with plaintext values to this public repository. For a shared or production cluster, manage these values with a dedicated secret-management workflow such as External Secrets, SOPS, or Sealed Secrets instead of manual bootstrap commands.
