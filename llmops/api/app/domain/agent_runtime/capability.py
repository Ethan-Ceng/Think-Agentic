from copy import deepcopy
from typing import Any

WORKER_CAPABILITY_SCHEMA_VERSION = "worker_capability_v2"
ROUTING_POLICY_SCHEMA_VERSION = "routing_policy_v1"

CAPABILITY_ERROR_MESSAGES: dict[str, str] = {
    "capability_missing:image_input": "当前绑定 Worker 不支持图片输入。",
    "capability_missing:file_input": "当前绑定 Worker 不支持文件输入。",
    "capability_missing:search": "当前绑定 Worker 不具备搜索或最新信息能力。",
    "worker_model_unsupported:image_input": "Worker 配置了图片能力，但当前模型不支持图片输入。",
    "worker_unavailable": "目标 Worker 当前不可用。",
    "external_agent_auth_required": "外部 Agent 需要认证，但当前未配置有效凭据。",
    "external_agent_protocol_error": "外部 Agent 协议调用失败或版本不兼容。",
    "routing_policy_invalid": "Worker 编排规则格式不正确。",
    "capability_summary_invalid": "Worker 能力摘要格式不正确。",
    "replan_limit_exceeded": "本次任务已达到自动重规划次数上限。",
}


def user_message_for_error(error_code: str) -> str:
    return CAPABILITY_ERROR_MESSAGES.get(error_code, "Worker 能力校验未通过。")


def default_routing_policy() -> dict[str, Any]:
    return deepcopy(
        {
            "schema_version": ROUTING_POLICY_SCHEMA_VERSION,
            "rules": [
                {
                    "id": "image_requires_vision",
                    "when": {"input_modality_any": ["image/png", "image/jpeg", "image/webp"]},
                    "require": {"input_modality_any": ["image/png", "image/jpeg", "image/webp"]},
                    "on_missing": "capability_missing:image_input",
                },
                {
                    "id": "latest_info_requires_search",
                    "when": {
                        "intent_keywords_any": [
                            "搜索",
                            "最新",
                            "预警",
                            "网页",
                            "来源",
                            "search",
                            "latest",
                            "news",
                            "web",
                            "source",
                        ],
                    },
                    "require": {"semantic_tags_any": ["search"]},
                    "on_missing": "capability_missing:search",
                },
            ],
            "fallback_policy": {
                "on_planner_invalid": "manager_rule_v1",
                "on_preflight_failed": "structured_error",
                "on_worker_failed": "replan_once",
            },
        }
    )


def normalize_routing_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    normalized = default_routing_policy()
    if not isinstance(policy, dict):
        return normalized

    merged = deepcopy(policy)
    merged["schema_version"] = str(merged.get("schema_version") or ROUTING_POLICY_SCHEMA_VERSION)
    if not isinstance(merged.get("rules"), list):
        merged["rules"] = normalized["rules"]
    if not isinstance(merged.get("fallback_policy"), dict):
        merged["fallback_policy"] = normalized["fallback_policy"]
    return merged


def validate_routing_policy(policy: dict[str, Any] | None) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if not isinstance(policy, dict):
        errors.append({"field": "routing_policy", "message": "routing_policy must be an object"})
        return False, errors, warnings

    schema_version = str(policy.get("schema_version") or "")
    if schema_version and schema_version != ROUTING_POLICY_SCHEMA_VERSION:
        errors.append(
            {
                "field": "schema_version",
                "message": f"schema_version must be {ROUTING_POLICY_SCHEMA_VERSION}",
            }
        )

    rules = policy.get("rules")
    if rules is not None and not isinstance(rules, list):
        errors.append({"field": "rules", "message": "rules must be a list"})
    elif isinstance(rules, list):
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append({"field": f"rules[{index}]", "message": "rule must be an object"})
                continue
            if not str(rule.get("id") or "").strip():
                warnings.append({"field": f"rules[{index}].id", "message": "rule id is empty"})
            if not isinstance(rule.get("when", {}), dict):
                errors.append({"field": f"rules[{index}].when", "message": "when must be an object"})
            if "require" in rule and not isinstance(rule.get("require"), dict):
                errors.append({"field": f"rules[{index}].require", "message": "require must be an object"})
            if "prefer" in rule and not isinstance(rule.get("prefer"), dict):
                errors.append({"field": f"rules[{index}].prefer", "message": "prefer must be an object"})

    fallback_policy = policy.get("fallback_policy")
    if fallback_policy is not None and not isinstance(fallback_policy, dict):
        errors.append({"field": "fallback_policy", "message": "fallback_policy must be an object"})

    return not errors, errors, warnings
