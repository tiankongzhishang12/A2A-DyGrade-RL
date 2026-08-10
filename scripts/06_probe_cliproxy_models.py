from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.utils.io import ensure_dir, read_yaml, write_json, write_yaml
from a2a_dygrade_rl.utils.llm_client import OpenAIResponsesClient


def main() -> None:
    parser = argparse.ArgumentParser(description="CLIProxy GPT-5.6 Luna/Terra/Sol模型身份探针")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--agents", nargs="+", choices=("CheapAgent", "MidAgent", "StrongAgent"), default=None)
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument("--max-output-tokens", type=int, default=64)
    args = parser.parse_args()
    if not args.run_id.startswith("real_pilot_"):
        parser.error("run-id必须使用real_pilot_前缀")
    config = read_yaml(args.config)
    provider = dict(config["provider"])
    provider["max_cost_usd"] = min(float(provider["max_cost_usd"]), 1.0)
    provider["max_total_calls"] = min(int(provider["max_total_calls"]), 6)
    provider["max_attempts"] = 2
    provider["timeout_seconds"] = min(float(provider.get("timeout_seconds", 180)), 90.0)
    probe_agents = {key: {**row, "generation_parameters": {"reasoning_effort": args.reasoning_effort, "max_output_tokens": args.max_output_tokens, "store": False}} for key, row in config["agents"].items()}
    client = OpenAIResponsesClient(provider=provider, agents=probe_agents)
    available_models = client.discover_models()
    request = {
        "item_id": "model_identity_probe",
        "dataset": "probe",
        "question_type": "short_answer",
        "subject": "probe",
        "prompt": "Give one point for the exact answer OK.",
        "student_answer": "OK",
        "reference_answer": "OK",
        "rubric": "Score 1 for exact OK, otherwise 0.",
        "score_range": {"min": 0.0, "max": 1.0},
        "prompt_template": "执行最小评分探针；必须返回合法结构化结果。",
        "prompt_version": "model-probe-v1",
        "role": "model_probe",
        "context": {},
    }
    rows = []
    selected_agents = tuple(args.agents or ("CheapAgent", "MidAgent", "StrongAgent"))
    for agent_id in selected_agents:
        configured = next(row for row in probe_agents.values() if row["agent_id"] == agent_id)
        try:
            response = client.complete(request, agent_id)
            rows.append({
                "agent_id": agent_id,
                "requested_model_id": configured["model_id"],
                "reported_model_id": response.metadata["reported_model_id"],
                "request_id": response.metadata["request_id"],
                "usage": response.usage.to_dict(),
                "cost_usd": response.cost,
                "latency": response.latency,
                "status": "pass",
                "error": None,
            })
        except Exception as exc:
            rows.append({
                "agent_id": agent_id,
                "requested_model_id": configured["model_id"],
                "reported_model_id": None,
                "request_id": None,
                "usage": None,
                "cost_usd": None,
                "latency": None,
                "status": "fail",
                "error": f"{type(exc).__name__}: {exc}",
            })
    run_dir = Path(args.output_root) / args.run_id
    ensure_dir(run_dir / "configs")
    ensure_dir(run_dir / "reports")
    write_yaml(run_dir / "configs" / "agents.resolved.yaml", config, overwrite=True)
    report = {
        "run_id": args.run_id,
        "execution_mode": "real_pilot",
        "probe_type": "cliproxy_model_identity",
        "formal_eligible": False,
        "available_models": available_models,
        "required_models": ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"],
        "all_required_models_available": all(model in available_models for model in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")),
        "records": rows,
        "budget": client.budget_snapshot(),
        "status": "pass" if all(row["status"] == "pass" for row in rows) else "fail",
    }
    write_json(run_dir / "reports" / "cliproxy_model_identity_probe.json", report, overwrite=True)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()



