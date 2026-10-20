"""Measure prebuilt-invoice usage without changing resource-level CU defaults."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_URL = (
    "https://github.com/Azure-Samples/azure-ai-content-understanding-python/"
    "raw/refs/heads/main/data/invoice.pdf"
)
MODEL_ALIASES = {"gpt-5.6-tera": "gpt-5.6-terra"}


def azure(*args):
    executable = shutil.which("az") or shutil.which("az.cmd")
    if executable is None:
        raise RuntimeError("Azure CLI is required; run az login before benchmarking")
    result = subprocess.run(
        [executable, *args, "-o", "json"], capture_output=True, text=True,
        encoding="utf-8", timeout=180,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else None


class ContentUnderstanding:
    def __init__(self, endpoint, key, api_version="2025-11-01"):
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
            raise ValueError("CU endpoint must be an HTTPS resource endpoint without credentials")
        self.endpoint = endpoint.rstrip("/")
        self.key = key
        self.api_version = api_version

    def request(self, path, body=None):
        url = path if path.startswith("https://") else (
            f"{self.endpoint}/contentunderstanding/{path}?api-version={self.api_version}"
        )
        if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(self.endpoint).netloc:
            raise ValueError("Polling URL must belong to the configured CU resource")
        request = urllib.request.Request(
            url, data=json.dumps(body).encode() if body is not None else None,
            headers={"Ocp-Apim-Subscription-Key": self.key, "Content-Type": "application/json"},
            method="POST" if body is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response), response.headers

    def analyze(self, sample_url, completion, embedding, timeout=240, deployment_retry_seconds=0):
        mappings = {"prebuilt-analyzer-completion": completion}
        if embedding is not None:
            mappings["prebuilt-analyzer-embedding"] = embedding
        body = {"inputs": [{"url": sample_url}], "modelDeployments": mappings}
        propagation_deadline = time.monotonic() + deployment_retry_seconds
        while True:
            try:
                _, headers = self.request("analyzers/prebuilt-invoice:analyze", body)
                break
            except urllib.error.HTTPError as error:
                detail = json.loads(error.read().decode()).get("error", {})
                inner = detail.get("innererror", {})
                if inner.get("code") != "DeploymentIdNotFound" or time.monotonic() >= propagation_deadline:
                    raise RuntimeError(f"HTTP {error.code}: {json.dumps(detail)}") from error
                print("Waiting for CU to discover the new model deployment...", flush=True)
                time.sleep(10)
        location = headers.get("Operation-Location")
        if not location:
            raise ValueError("Analyze response has no Operation-Location")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response, _ = self.request(location)
            status = response.get("status", "").lower()
            if status == "succeeded":
                return response
            if status in ("failed", "canceled", "cancelled"):
                raise RuntimeError(json.dumps(response.get("error", {"status": status})))
            time.sleep(2)
        raise TimeoutError(f"Invoice analysis exceeded {timeout} seconds")


def summarize_usage(response, model_name):
    usage = response.get("usage", response.get("result", {}).get("usage"))
    if not isinstance(usage, dict):
        raise ValueError("Successful analysis did not report usage")
    pages = sum(usage.get(key, 0) for key in (
        "documentPagesBasic", "documentPagesStandard", "documentPagesMinimal",
    ))
    if not isinstance(pages, (int, float)) or pages <= 0:
        raise ValueError("Invoice usage did not report a positive page count")
    tokens = usage.get("tokens", {})
    expected_input = f"{model_name}-input"
    expected_output = f"{model_name}-output"
    if expected_input not in tokens or expected_output not in tokens:
        raise ValueError(f"Usage does not confirm the requested completion model {model_name}")
    cached_keys = [key for key in tokens if key.startswith(f"{model_name}-") and "cached" in key]
    cached = sum(tokens[key] for key in cached_keys) if cached_keys else None
    context = usage.get("contextualizationTokens", usage.get("contextualizationToken"))
    if context is None:
        raise ValueError("Invoice usage did not report contextualization tokens")
    embeddings = sum(value for key, value in tokens.items() if key.startswith("text-embedding-"))
    for value in [pages, tokens[expected_input], tokens[expected_output], context, embeddings, cached]:
        if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
            raise ValueError("Usage contains an invalid count")
    if cached is not None and cached > tokens[expected_input]:
        raise ValueError("Cached tokens exceed total input")
    return {
        "pages": pages, "input": tokens[expected_input], "output": tokens[expected_output],
        "cached_input": cached, "contextualization": context, "embeddings": embeddings,
        "usage": usage,
    }


def aggregate_runs(runs):
    if not runs:
        raise ValueError("At least one measured run is required")
    pages = sum(run["pages"] for run in runs)
    return {
        key: None if any(run[key] is None for run in runs)
        else sum(run[key] for run in runs) / pages
        for key in ("input", "cached_input", "output", "contextualization", "embeddings")
    }


def resume_records(previous, snapshot):
    for key in ("sampleSha256", "runsPerModel"):
        if previous[key] != snapshot[key]:
            raise ValueError(f"Cannot resume benchmark with different {key}")
    records = previous["models"]
    for record in records.values():
        for key in ("apiVersion", "region", "measuredAt", "embeddingModel"):
            if key in previous:
                record.setdefault(key, previous[key])
    return records


def write_snapshot(path, snapshot):
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    for attempt in range(10):
        try:
            temporary_path.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1 * (attempt + 1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--subscription", help="Azure subscription containing the benchmark resource")
    parser.add_argument("--sample-url", default=SAMPLE_URL)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--api-version", default="2025-11-01")
    parser.add_argument("--models", nargs="+", help="Limit measurements to these model names")
    parser.add_argument("--resume", action="store_true", help="Retain other model records from an existing matching snapshot")
    parser.add_argument("--deploy-missing", action="store_true",
                        help="Temporarily create PAYG deployments if quota permits; delete them after each model")
    parser.add_argument("--output", type=Path, default=ROOT / "src" / "lib" / "invoice-token-defaults.json")
    args = parser.parse_args(argv)
    if args.runs < 1 or args.runs > 10:
        parser.error("--runs must be between 1 and 10")
    if not args.sample_url.startswith("https://"):
        parser.error("--sample-url must be HTTPS")
    account_args = ["--name", args.account, "--resource-group", args.resource_group]
    subscription_args = ["--subscription", args.subscription] if args.subscription else []
    account_args.extend(subscription_args)
    account = azure("cognitiveservices", "account", "show", *account_args)
    key = azure("cognitiveservices", "account", "keys", "list", *account_args)["key1"]
    client = ContentUnderstanding(account["properties"]["endpoint"], key, args.api_version)
    analyzer, _ = client.request("analyzers/prebuilt-invoice")
    supported = analyzer["supportedModels"]["completion"]
    deployments = azure("cognitiveservices", "account", "deployment", "list", *account_args)
    embedding = next((item for item in deployments
                      if item["properties"]["model"]["name"] == "text-embedding-3-large"), None)
    with urllib.request.urlopen(args.sample_url, timeout=60) as response:
        sample = response.read()
    if not sample.startswith(b"%PDF"):
        raise ValueError("The sample URL must point to an actual PDF, not a Git LFS pointer")
    names = json.loads((ROOT / "src" / "lib" / "azure-openai-pricing.json").read_text())["models"]
    catalog = azure("cognitiveservices", "account", "list-models", *account_args) if args.deploy_missing else []
    quota = azure("cognitiveservices", "usage", "list", "--location", account["location"], *subscription_args) if args.deploy_missing else []
    snapshot = {
        "analyzerId": "prebuilt-invoice", "apiVersion": args.api_version,
        "measuredAt": datetime.now(timezone.utc).isoformat(),
        "region": account["location"],
        "sampleUrl": args.sample_url, "sampleSha256": hashlib.sha256(sample).hexdigest(),
        "sampleBytes": len(sample), "runsPerModel": args.runs,
        "embeddingModel": "text-embedding-3-large" if embedding else None,
        "supportedCompletionModels": supported,
        "notes": [
            "Only document-page defaults are measured; invoice PDFs cannot calibrate audio, video, text or image workloads.",
            "Absent cached-input counters mean not reported, not measured zero; the calculator retains a zero-cache assumption.",
            "Embedding defaults reflect billed embedding usage for this prebuilt analyzer, not all CU analyzers.",
            "Unsupported models retain heuristic defaults; request mappings never change resource-level defaults.",
        ],
        "models": {},
    }
    if args.resume:
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        snapshot["models"] = resume_records(previous, snapshot)

    def save():
        write_snapshot(args.output, snapshot)

    for name in names:
        if args.models and name not in args.models:
            snapshot["models"].setdefault(name, {
                "status": "not_requested", "reason": "Not selected for this benchmark run",
            })
            continue
        model_name = MODEL_ALIASES.get(name, name)
        record = {
            "status": "unsupported",
            "reason": f"Not supported by prebuilt-invoice in {account['location']} with API {args.api_version}",
            "modelName": model_name, "apiVersion": args.api_version, "region": account["location"],
            "measuredAt": snapshot["measuredAt"], "embeddingModel": snapshot["embeddingModel"],
        }
        snapshot["models"][name] = record
        if model_name not in supported:
            save()
            continue
        record.pop("reason")
        deployment = next((item for item in deployments if item["properties"]["model"]["name"] == model_name), None)
        temporary = None
        try:
            if deployment is None and args.deploy_missing:
                available = next((model for model in catalog if model["name"] == model_name
                                  and model.get("isDefaultVersion")), None)
                if available is None:
                    available = next((model for model in catalog if model["name"] == model_name), None)
                candidates = [
                    sku for sku in ("GlobalStandard", "DataZoneStandard", "Standard")
                    if available and any(item["name"] == sku for item in available["skus"])
                    and any(item["name"]["value"] == f"OpenAI.{sku}.{model_name}"
                            and item["limit"] - item["currentValue"] >= 50 for item in quota)
                ]
                if candidates:
                    temporary = f"cu-price-bench-{uuid.uuid4().hex[:10]}"
                    print(f"{name}: creating temporary {candidates[0]} PAYG deployment", flush=True)
                    deployment = azure(
                        "cognitiveservices", "account", "deployment", "create", *account_args,
                        "--deployment-name", temporary, "--model-name", model_name,
                        "--model-version", available["version"], "--model-format", available["format"],
                        "--sku-name", candidates[0], "--sku-capacity", "50",
                    )
                    time.sleep(15)
            if deployment is None:
                record.update(status="not_deployed", reason="No existing deployment or sufficient free quota for a temporary PAYG deployment")
                print(f"{name}: not deployed / quota unavailable", flush=True)
                continue
            record.update(status="running", modelVersion=deployment["properties"]["model"]["version"],
                          deploymentType=deployment.get("sku", {}).get("name"), runs=[])
            for index in range(args.runs):
                print(f"{name}: invoice run {index + 1}/{args.runs}", flush=True)
                measured = summarize_usage(client.analyze(
                    args.sample_url, deployment["name"], embedding["name"] if embedding else None,
                    deployment_retry_seconds=180 if temporary else 0,
                ), model_name)
                measured["measuredAt"] = datetime.now(timezone.utc).isoformat()
                record["runs"].append(measured)
                save()
            record.update(status="measured", perPage=aggregate_runs(record["runs"]))
            print(f"{name}: {json.dumps(record['perPage'])}", flush=True)
        except urllib.error.HTTPError as error:
            detail = json.loads(error.read().decode()).get("error", {})
            record.update(status="failed", reason=f"HTTP {error.code}: {detail.get('code', 'UnknownError')}: {detail.get('message', '')}")
            record["error"] = detail
            print(f"{name}: {record['reason']}", file=sys.stderr, flush=True)
        except (ValueError, RuntimeError, TimeoutError, urllib.error.URLError) as error:
            record.update(status="failed", reason=str(error))
            print(f"{name}: {error}", file=sys.stderr, flush=True)
        finally:
            if temporary:
                azure("cognitiveservices", "account", "deployment", "delete", *account_args,
                      "--deployment-name", temporary)
                print(f"{name}: removed temporary deployment", flush=True)
            save()
    save()
    measured = sum(record["status"] == "measured" for record in snapshot["models"].values())
    print(f"Saved {measured}/{len(names)} measured document defaults to {args.output}")
    expected = [name for name in names if MODEL_ALIASES.get(name, name) in supported
                and (not args.models or name in args.models)]
    succeeded = sum(snapshot["models"][name]["status"] == "measured" for name in expected)
    return 0 if expected and succeeded == len(expected) else 2


if __name__ == "__main__":
    raise SystemExit(main())
