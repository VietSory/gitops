#!/usr/bin/env python3
"""Repository-specific deployment invariants that schema validation cannot prove."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIRS = (ROOT / "k8s", ROOT / "k8s-api", ROOT / "argocd")
WORKLOAD_KINDS = {"Deployment", "Rollout"}

Document = tuple[Path, int, dict[str, Any]]


def identity(document: dict[str, Any]) -> str:
    metadata = document.get("metadata") or {}
    namespace = metadata.get("namespace", "default")
    return f"{document.get('kind', '<unknown>')}/{namespace}/{metadata.get('name', '<unnamed>')}"


def load_documents(errors: list[str]) -> list[Document]:
    documents: list[Document] = []

    for directory in MANIFEST_DIRS:
        if not directory.is_dir():
            errors.append(f"missing manifest directory: {directory.relative_to(ROOT)}")
            continue

        for path in sorted(directory.rglob("*.yaml")):
            try:
                parsed = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            except yaml.YAMLError as exc:
                errors.append(f"{path.relative_to(ROOT)}: invalid YAML: {exc}")
                continue

            for index, document in enumerate(parsed, start=1):
                if document is None:
                    continue
                if not isinstance(document, dict):
                    errors.append(
                        f"{path.relative_to(ROOT)} document {index}: expected a mapping"
                    )
                    continue
                documents.append((path, index, document))

    return documents


def find_document(
    documents: list[Document], kind: str, name: str
) -> tuple[Path, dict[str, Any]] | None:
    matches = [
        (path, document)
        for path, _, document in documents
        if document.get("kind") == kind
        and (document.get("metadata") or {}).get("name") == name
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def validate_workloads(documents: list[Document], errors: list[str]) -> None:
    workload_labels: list[tuple[str, dict[str, str], str]] = []

    for _, _, document in documents:
        if document.get("kind") not in WORKLOAD_KINDS:
            continue

        label = identity(document)
        spec = document.get("spec") or {}
        template = spec.get("template") or {}
        template_metadata = template.get("metadata") or {}
        pod_spec = template.get("spec") or {}

        if pod_spec.get("automountServiceAccountToken") is not False:
            errors.append(f"{label}: automountServiceAccountToken must be false")

        labels = template_metadata.get("labels") or {}
        namespace = (document.get("metadata") or {}).get("namespace", "default")
        if not labels:
            errors.append(f"{label}: pod template must declare labels")
        else:
            workload_labels.append((namespace, labels, label))

        containers = pod_spec.get("containers") or []
        if not containers:
            errors.append(f"{label}: pod template must declare at least one container")
            continue

        for container in containers:
            container_name = container.get("name", "<unnamed>")
            prefix = f"{label} container {container_name}"
            image = container.get("image", "")
            if not image:
                errors.append(f"{prefix}: image is required")
            elif image.endswith(":latest") or ":latest@" in image:
                errors.append(f"{prefix}: mutable :latest image tag is forbidden")

            resources = container.get("resources") or {}
            if not resources.get("requests") or not resources.get("limits"):
                errors.append(f"{prefix}: resource requests and limits are required")

            if not container.get("readinessProbe"):
                errors.append(f"{prefix}: readinessProbe is required")
            if not container.get("livenessProbe"):
                errors.append(f"{prefix}: livenessProbe is required")

    for _, _, document in documents:
        if document.get("kind") != "Service":
            continue

        selector = (document.get("spec") or {}).get("selector") or {}
        if not selector:
            continue

        metadata = document.get("metadata") or {}
        namespace = metadata.get("namespace", "default")
        service_id = identity(document)
        matches = [
            workload_id
            for workload_namespace, labels, workload_id in workload_labels
            if workload_namespace == namespace
            and all(labels.get(key) == value for key, value in selector.items())
        ]
        if not matches:
            errors.append(f"{service_id}: selector does not match any workload pod labels")


def validate_canary_analysis(documents: list[Document], errors: list[str]) -> None:
    rollout_match = find_document(documents, "Rollout", "api")
    template_match = find_document(documents, "AnalysisTemplate", "api-error-rate")
    monitor_match = find_document(documents, "ServiceMonitor", "api")

    if rollout_match is None:
        errors.append("expected exactly one Rollout named api")
        return
    if template_match is None:
        errors.append("expected exactly one AnalysisTemplate named api-error-rate")
        return
    if monitor_match is None:
        errors.append("expected exactly one ServiceMonitor named api")
        return

    _, rollout = rollout_match
    _, template = template_match
    _, monitor = monitor_match

    template_spec = template.get("spec") or {}
    declared_args = {
        arg.get("name")
        for arg in template_spec.get("args") or []
        if isinstance(arg, dict)
    }
    if "latest-hash" not in declared_args:
        errors.append("AnalysisTemplate/api-error-rate: latest-hash arg is required")

    metrics = template_spec.get("metrics") or []
    query = ""
    if metrics:
        query = (
            (((metrics[0].get("provider") or {}).get("prometheus") or {}).get("query"))
            or ""
        )
    revision_filter = 'rollout_revision="{{args.latest-hash}}"'
    if query.count(revision_filter) < 2:
        errors.append(
            "AnalysisTemplate/api-error-rate: numerator and denominator must both "
            "filter on the latest rollout revision"
        )

    canary = (((rollout.get("spec") or {}).get("strategy") or {}).get("canary") or {})
    analysis_steps = [
        step.get("analysis")
        for step in canary.get("steps") or []
        if isinstance(step, dict) and step.get("analysis")
    ]
    if not analysis_steps:
        errors.append("Rollout/api: at least one inline analysis step is required")

    for index, analysis in enumerate(analysis_steps, start=1):
        args = analysis.get("args") or []
        latest_hash = next(
            (
                arg
                for arg in args
                if isinstance(arg, dict) and arg.get("name") == "latest-hash"
            ),
            None,
        )
        value_from = (latest_hash or {}).get("valueFrom") or {}
        if value_from.get("podTemplateHashValue") != "Latest":
            errors.append(
                f"Rollout/api analysis step {index}: latest-hash must come from "
                "podTemplateHashValue=Latest"
            )

    endpoints = (monitor.get("spec") or {}).get("endpoints") or []
    relabelings = [
        relabel
        for endpoint in endpoints
        for relabel in (endpoint.get("relabelings") or [])
        if isinstance(relabel, dict)
    ]
    expected_source = "__meta_kubernetes_pod_label_rollouts_pod_template_hash"
    if not any(
        relabel.get("targetLabel") == "rollout_revision"
        and expected_source in (relabel.get("sourceLabels") or [])
        for relabel in relabelings
    ):
        errors.append(
            "ServiceMonitor/api: rollout pod-template hash must be relabeled to "
            "rollout_revision"
        )


def validate_monitoring_secrets(documents: list[Document], errors: list[str]) -> None:
    application_match = find_document(documents, "Application", "kube-prometheus-stack")
    if application_match is None:
        errors.append("expected exactly one Application named kube-prometheus-stack")
        return

    path, application = application_match
    source = (application.get("spec") or {}).get("source") or {}
    values_text = ((source.get("helm") or {}).get("values")) or ""
    try:
        values = yaml.safe_load(values_text) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{path.relative_to(ROOT)}: invalid embedded Helm values: {exc}")
        return

    grafana = values.get("grafana") or {}
    if "adminPassword" in grafana:
        errors.append("Grafana adminPassword must not be stored in Git")

    admin = grafana.get("admin") or {}
    expected_admin = {
        "existingSecret": "grafana-admin-credentials",
        "userKey": "admin-user",
        "passwordKey": "admin-password",
    }
    for key, expected in expected_admin.items():
        if admin.get(key) != expected:
            errors.append(f"Grafana admin.{key} must be {expected!r}")

    alertmanager = values.get("alertmanager") or {}
    global_config = ((alertmanager.get("config") or {}).get("global")) or {}
    if global_config.get("smtp_auth_password"):
        errors.append("Alertmanager SMTP password must not be stored inline")
    if not global_config.get("smtp_auth_password_file"):
        errors.append("Alertmanager must read its SMTP password from a mounted secret file")


def main() -> int:
    errors: list[str] = []
    documents = load_documents(errors)

    validate_workloads(documents, errors)
    validate_canary_analysis(documents, errors)
    validate_monitoring_secrets(documents, errors)

    if errors:
        print("Repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Repository validation passed for {len(documents)} manifest documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
