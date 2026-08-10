"""100 Item真实Agent Pilot的模型与Arbitrator context比较。"""
from __future__ import annotations

import csv, json
from collections import defaultdict
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.agents.pricing import TokenUsage, compute_api_cost, load_pricing_manifest
from a2a_dygrade_rl.utils.io import ensure_dir, read_jsonl, write_json

ROLE_ORDER={"CheapAgent":0,"MidAgent":1,"StrongAgent":2}

def _err(r):
    return abs(float(r["pred_score"])-float(r["gold_score"]))/max(1e-12,float(r["metadata"]["score_max"])-float(r["metadata"]["score_min"]))

def _summary(rows):
    errors=[_err(r) for r in rows]
    return {"n":len(rows),"nmae":sum(errors)/len(errors) if errors else None,"severe_rate":sum(e>0.25 for e in errors)/len(errors) if errors else None,"extreme_rate":sum(e>=0.5 for e in errors)/len(errors) if errors else None,"mean_cost":sum(float(r["cost"]) for r in rows)/len(rows) if rows else None,"mean_latency":sum(float(r["latency"]) for r in rows)/len(rows) if rows else None}

def analyze_pilot(
    run_dir: str | Path,
    split: str = "train_fit",
    pricing_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    root=Path(run_dir); cache=root/"predictions"/"agent_cache"/split
    records=[]
    for p in sorted(cache.glob("*.jsonl")): records.extend(read_jsonl(p))
    pricing = load_pricing_manifest(pricing_manifest_path) if pricing_manifest_path else None
    if pricing is not None:
        repriced=[]
        for record in records:
            row=dict(record)
            if row.get("status")=="success":
                usage=TokenUsage(
                    input_tokens=int(row.get("input_tokens",0)),
                    cached_input_tokens=int(row.get("cached_input_tokens",0)),
                    cache_write_tokens=int(row.get("cache_write_tokens",0)),
                    output_tokens=int(row.get("output_tokens",0)),
                    reasoning_tokens=int(row.get("reasoning_tokens",0)),
                    total_tokens=int(row.get("token_usage",0)),
                )
                row["cost"]=compute_api_cost(usage,pricing.rule_for(str(row["model_id"])))
            repriced.append(row)
        records=repriced
    success=[r for r in records if r.get("status")=="success"]
    by_item=defaultdict(dict); contexts=defaultdict(list)
    for r in success:
        if r["agent_id"]=="ArbitratorAgent":
            key="+".join(r.get("metadata",{}).get("context_agents",[])); contexts[key].append(r)
        else: by_item[r["item_id"]][r["agent_id"]]=r
    context_rows=[]
    for key,rows in sorted(contexts.items()):
        agents=key.split("+") if key else []
        strongest=[]; means=[]; weighted=[]
        cumulative=[]
        for r in rows:
            visible=[by_item[r["item_id"]][a] for a in agents]
            scorers=[v for v in visible if v["agent_id"] in ROLE_ORDER]
            strongest.append(max(scorers,key=lambda v:ROLE_ORDER[v["agent_id"]]))
            base=visible[0]
            mean_score=sum(float(v["pred_score"]) for v in visible)/len(visible)
            total_conf=sum(max(.01,float(v["confidence"])) for v in visible)
            weighted_score=sum(float(v["pred_score"])*max(.01,float(v["confidence"])) for v in visible)/total_conf
            means.append({**base,"pred_score":mean_score})
            weighted.append({**base,"pred_score":weighted_score})
            cumulative.append(sum(float(v["cost"]) for v in visible)+float(r["cost"]))
        s=_summary(rows); bs=_summary(strongest); ms=_summary(means); ws=_summary(weighted)
        group="evidence" if "EvidenceAgent" in agents else ("pair" if len(agents)==2 else "scorer_full")
        context_rows.append({"context_id":key,"group":group,**s,"cumulative_mean_cost":sum(cumulative)/len(cumulative),"delta_nmae_vs_strongest":s["nmae"]-bs["nmae"],"delta_severe_vs_strongest":s["severe_rate"]-bs["severe_rate"],"delta_nmae_vs_mean":s["nmae"]-ms["nmae"],"delta_nmae_vs_conf_weighted":s["nmae"]-ws["nmae"]})
    for row in context_rows:
        peers=[p for p in context_rows if p["group"]==row["group"] and p is not row]
        row["pareto_dominated"]=any(p["nmae"]<=row["nmae"] and p["severe_rate"]<=row["severe_rate"] and p["cumulative_mean_cost"]<=row["cumulative_mean_cost"] and (p["nmae"]<row["nmae"] or p["severe_rate"]<row["severe_rate"] or p["cumulative_mean_cost"]<row["cumulative_mean_cost"]) for p in peers)
        row["recommendation"]="retain_candidate" if not row["pareto_dominated"] and (row["delta_nmae_vs_strongest"]<0 or row["delta_nmae_vs_mean"]<0 or row["delta_nmae_vs_conf_weighted"]<0) and row["delta_severe_vs_strongest"]<=0 else "review_or_reject"
    agent_rows=[]
    for aid in ("CheapAgent","MidAgent","StrongAgent","EvidenceAgent"):
        rows=[r for r in success if r["agent_id"]==aid]; agent_rows.append({"agent_id":aid,**_summary(rows)})
    reports=ensure_dir(root/"reports")
    _csv(reports/"agent_quality_cost.csv",agent_rows); _csv(reports/"arbitrator_context_selection.csv",context_rows)
    result={"run_id":root.name,"record_count":len(records),"success_count":len(success),"failure_count":len(records)-len(success),"agents":agent_rows,"contexts":context_rows,"formal_catalog_frozen":False,"pricing_effective_date":pricing.effective_date if pricing else None,"pricing_manifest_sha256":pricing.sha256 if pricing else None}
    write_json(reports/"cliproxy_100_item_pilot_analysis.json",result,overwrite=True)
    return result

def _csv(path,rows):
    if not rows:return
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
