"""Run a fixture-cache preliminary routing validation."""
from __future__ import annotations
import argparse, json, sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from a2a_dygrade_rl.evaluation.preliminary_validation import (
    confidence_policy, deterministic_partition, evaluate_selections,
    load_agent_cache, oracle_policy, select_threshold, static_policy, write_csv,
)

def args():
    p=argparse.ArgumentParser()
    p.add_argument("--source-run-id", default="fixture_smoke_001")
    p.add_argument("--run-id", required=True)
    p.add_argument("--cost-weight", type=float, default=4.0)
    return p.parse_args()

def main():
    a=args(); source=ROOT/"outputs"/"runs"/a.source_run_id/"predictions"/"agent_cache"/"train"
    out=ROOT/"outputs"/"runs"/a.run_id
    if out.exists(): raise FileExistsError(f"run_id exists: {out}")
    caches=load_agent_cache(source,["CheapAgent","MidAgent","StrongAgent"])
    ids=sorted(caches["CheapAgent"]); cal,ev=deterministic_partition(ids)
    thresholds=[round(x/20,2) for x in range(5,16)]
    threshold,trials=select_threshold(cal,caches,thresholds,a.cost_weight)
    results=[]
    for agent,method in [("CheapAgent","Cheap-only"),("MidAgent","Mid-only"),("StrongAgent","Strong-only")]:
        results.append(evaluate_selections(method,"evaluation",ev,caches,static_policy(agent,ev)))
    results.append(evaluate_selections("Confidence Router (Cheap->Mid)","evaluation",ev,caches,confidence_policy(ev,caches,threshold),threshold))
    results.append(evaluate_selections("Oracle Router (diagnostic upper bound)","evaluation",ev,caches,oracle_policy(ev,caches,["CheapAgent","MidAgent","StrongAgent"])))
    for d in [out/"configs",out/"reports",out/"logs"]: d.mkdir(parents=True)
    config={"run_id":a.run_id,"source_run_id":a.source_run_id,"source_split":"train","uses_test_split":False,"fixture_only":True,"partition_rule":"SHA256(item_id): first 50% calibration, rest evaluation","calibration_item_ids":cal,"evaluation_item_ids":ev,"threshold_candidates":thresholds,"cost_weight":a.cost_weight,"selected_threshold":threshold,"created_at_utc":datetime.now(timezone.utc).isoformat()}
    (out/"configs"/"preliminary_validation.json").write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding="utf-8")
    write_csv(out/"reports"/"threshold_calibration.csv",trials)
    rows=[asdict(x) for x in results]; write_csv(out/"reports"/"preliminary_results.csv",rows)
    cheap=next(x for x in rows if x["method"]=="Cheap-only"); router=next(x for x in rows if x["method"].startswith("Confidence")); oracle=next(x for x in rows if x["method"].startswith("Oracle"))
    mae_gain=(cheap["normalized_mae"]-router["normalized_mae"])/cheap["normalized_mae"]
    oracle_gain=(cheap["normalized_mae"]-oracle["normalized_mae"])/cheap["normalized_mae"]
    lines=["# \u5c0f\u89c4\u6a21\u673a\u5236\u9884\u9a8c\u8bc1\u62a5\u544a","","## \u5b9e\u9a8c\u5b9a\u4f4d","",f"\u672c\u5b9e\u9a8c\u53ea\u4f7f\u7528 `{a.source_run_id}` \u7684 **train fixture cache**\uff0c\u4e0d\u8bfb\u53d6 dev/test\uff0c\u4e0d\u8bad\u7ec3\u6b63\u5f0f Router\u3002",f"- \u603b\u6837\u672c\u6570\uff1a{len(ids)}","- calibration/evaluation\uff1a10/10",f"- \u9009\u5b9a\u9608\u503c\uff1a{threshold:.2f}","- test split \u4f7f\u7528\uff1a\u5426","","## Evaluation \u7ed3\u679c","","| Method | N | normalized MAE \u2193 | normalized QWK \u2191 | mean cost \u2193 | mean latency \u2193 | upgrade rate |","|---|---:|---:|---:|---:|---:|---:|"]
    for x in rows: lines.append(f"| {x['method']} | {x['sample_count']} | {x['normalized_mae']:.4f} | {x['normalized_qwk']:.4f} | {x['mean_cost']:.4f} | {x['mean_latency']:.3f} | {x['upgrade_rate']:.1%} |")
    lines += ["","## \u521d\u6b65\u89c2\u5bdf","",f"1. \u76f8\u5bf9 Cheap-only\uff0c\u7f6e\u4fe1\u5ea6 Router \u7684 normalized MAE \u6539\u5584\u4e3a **{mae_gain:.1%}**\uff0c\u672c\u6b21\u6ca1\u6709\u5b66\u5230\u6709\u6548\u5347\u7ea7\u7b56\u7565\u3002",f"2. Oracle Router \u7684 normalized MAE \u76f8\u5bf9 Cheap-only \u6539\u5584 **{oracle_gain:.1%}**\uff0c\u8868\u660e fixture Agent \u4e4b\u95f4\u5b58\u5728\u4e00\u5b9a\u4e92\u8865\u6027\u548c\u8def\u7531\u4e0a\u754c\u7a7a\u95f4\u3002","3. Oracle \u4f7f\u7528 gold score \u9009\u62e9 Agent\uff0c\u4e0d\u80fd\u4f5c\u4e3a\u53ef\u90e8\u7f72\u65b9\u6cd5\u6216\u6b63\u5f0f baseline\u3002","","## \u5c40\u9650","","1. Agent \u8f93\u51fa\u6765\u81ea\u786e\u5b9a\u6027 fixture\uff0c\u4e0d\u662f\u771f\u5b9e LLM \u8c03\u7528\u3002",f"2. evaluation \u4ec5 {len(ev)} \u6761\u6837\u672c\uff0c\u4e0d\u80fd\u8fdb\u884c\u53ef\u9760\u663e\u8457\u6027\u63a8\u65ad\u3002","3. \u5f53\u524d\u4e0d\u5305\u542b A2A \u901a\u4fe1\u3001paper budget\u3001\u8f68\u8ff9\u5b66\u4e60\u6216 CAG-CQL\u3002","4. \u7ed3\u679c\u53ea\u652f\u6301\u673a\u5236\u53ef\u884c\u6027\u5206\u6790\uff1b\u6b63\u5f0f\u7ed3\u8bba\u9700\u8981\u771f\u5b9e Agent cache\u3001\u72ec\u7acb dev \u8c03\u53c2\u548c\u4e00\u6b21\u6027 test final evaluation\u3002"]
    report="\n".join(lines)+"\n"; (out/"reports"/"preliminary_validation.md").write_text(report,encoding="utf-8")
    (out/"logs"/"run.log").write_text(f"run_id={a.run_id}\nselected_threshold={threshold}\n",encoding="utf-8")
    print(report)
if __name__=="__main__": main()
