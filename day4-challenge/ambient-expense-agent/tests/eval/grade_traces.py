import os
import json
import yaml
import datetime
from pathlib import Path
from typing import Any

# Ensure standard import paths
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from google import genai
from rich.console import Console
from rich.table import Table

def load_eval_config(config_path: Path) -> tuple[list[str], dict[str, Any]]:
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    metrics_to_run = data.get("metrics_to_run", [])
    custom_metrics = {m["name"]: m for m in data.get("custom_metrics", [])}
    return metrics_to_run, custom_metrics

def main():
    console = Console()
    
    traces_path = Path("artifacts/traces/generated_traces.json")
    config_path = Path("tests/eval/eval_config.yaml")
    output_dir = Path("artifacts/eval")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not traces_path.exists():
        console.print(f"[red]Error: Traces file not found at {traces_path}. Please run generate-traces first.[/red]")
        sys.exit(1)
        
    metrics_to_run, custom_metrics = load_eval_config(config_path)
    
    with open(traces_path, "r", encoding="utf-8") as f:
        traces_data = json.load(f)
        
    cases = traces_data.get("eval_cases", [])
    console.print(f"Loaded {len(cases)} eval cases from traces.")
    
    # Initialize genai client
    client = genai.Client()
    
    results_cases = []
    metric_sums = {m: 0.0 for m in metrics_to_run}
    metric_counts = {m: 0 for m in metrics_to_run}
    
    # Per-case evaluations
    for case in cases:
        case_id = case["eval_case_id"]
        prompt_content = case["prompt"]
        prompt_text = prompt_content["parts"][0]["text"]
        
        response_content = case["responses"][0]["response"]
        response_text = response_content["parts"][0]["text"]
        
        agent_data = case["agent_data"]
        
        case_results = {
            "eval_case_id": case_id,
            "metrics": {}
        }
        
        console.print(f"Grading case: [cyan]{case_id}[/cyan]...")
        
        for m_name in metrics_to_run:
            if m_name not in custom_metrics:
                console.print(f"[yellow]Warning: Metric {m_name} not defined in custom_metrics. Skipping.[/yellow]")
                continue
                
            metric_def = custom_metrics[m_name]
            prompt_template = metric_def["prompt_template"]
            
            # Format template
            grading_prompt = prompt_template.replace("{prompt}", prompt_text)
            grading_prompt = grading_prompt.replace("{response}", response_text)
            grading_prompt = grading_prompt.replace("{agent_data}", json.dumps(agent_data, indent=2))
            
            # Sleep to avoid rate limits (5 RPM limit is very low)
            import time
            console.print(f"  Waiting 15s to respect rate limits...")
            time.sleep(15)
            
            # Run LLM-as-judge with exponential backoff retries
            max_retries = 5
            score = 1
            explanation = "Failed to grade metric due to API errors."
            for attempt in range(max_retries):
                try:
                    console.print(f"  Calling Gemini API for metric: {m_name} (attempt {attempt + 1})...")
                    response = client.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=grading_prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    res_json = json.loads(response.text)
                    score = int(res_json.get("score", 1))
                    explanation = res_json.get("explanation", "No explanation provided.")
                    break
                except Exception as e:
                    err_str = str(e)
                    err_repr = repr(e)
                    err_lower = err_str.lower() + " " + err_repr.lower()
                    
                    is_rate_limit = (
                        "429" in err_lower
                        or "503" in err_lower
                        or "resource_exhausted" in err_lower
                        or "unavailable" in err_lower
                        or "quota" in err_lower
                        or "limit" in err_lower
                        or getattr(e, "code", None) in [429, 503]
                        or getattr(e, "status", None) in ["RESOURCE_EXHAUSTED", "UNAVAILABLE"]
                    )
                    
                    if is_rate_limit:
                        console.print(f"[yellow]  Rate limit/quota/unavailable hit. Waiting 70s before retry... Error: {e}[/yellow]")
                        time.sleep(70)
                    elif attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + 2
                        console.print(f"[yellow]  Retrying grading metric {m_name} in {wait_time}s due to error: {e}[/yellow]")
                        time.sleep(wait_time)
                    else:
                        console.print(f"[red]Error grading metric {m_name} on case {case_id}: {e}[/red]")
                        score = 1
                        explanation = f"Failed to grade metric: {e}"
                
            case_results["metrics"][m_name] = {
                "score": score,
                "explanation": explanation
            }
            
            metric_sums[m_name] += score
            metric_counts[m_name] += 1
            
        results_cases.append(case_results)
        
    # Compile summary metrics
    summary_metrics = []
    for m_name in metrics_to_run:
        count = metric_counts[m_name]
        mean_score = metric_sums[m_name] / count if count > 0 else 0.0
        summary_metrics.append({
            "metric_name": m_name,
            "mean_score": mean_score
        })
        
    # Output JSON results
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    json_output_path = output_dir / f"results_{timestamp}.json"
    html_output_path = output_dir / f"results_{timestamp}.html"
    
    # Also save as latest results
    latest_json_path = output_dir / "results.json"
    latest_html_path = output_dir / "results.html"
    
    results_dump = {
        "summary_metrics": summary_metrics,
        "eval_cases": results_cases
    }
    
    for path in [json_output_path, latest_json_path]:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results_dump, f, indent=2)
            
    # Simple HTML report
    html_content = f"""
    <html>
    <head>
        <title>Evaluation Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background-color: #f9f9f9; color: #333; }}
            h1, h2 {{ color: #444; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; background: white; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .score {{ font-weight: bold; color: green; }}
        </style>
    </head>
    <body>
        <h1>Evaluation Results Summary</h1>
        <p>Executed at: {datetime.datetime.now().isoformat()}</p>
        
        <h2>Metrics Summary</h2>
        <table>
            <tr><th>Metric Name</th><th>Mean Score</th></tr>
    """
    for sm in summary_metrics:
        html_content += f"<tr><td>{sm['metric_name']}</td><td class='score'>{sm['mean_score']:.4f}</td></tr>"
        
    html_content += """
        </table>
        <h2>Per-Case Explanations</h2>
        <table>
            <tr><th>Case ID</th><th>Metric</th><th>Score</th><th>Explanation</th></tr>
    """
    for c_res in results_cases:
        c_id = c_res["eval_case_id"]
        for m_name, grade in c_res["metrics"].items():
            html_content += f"<tr><td>{c_id}</td><td>{m_name}</td><td class='score'>{grade['score']}</td><td>{grade['explanation']}</td></tr>"
            
    html_content += """
        </table>
    </body>
    </html>
    """
    
    for path in [html_output_path, latest_html_path]:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
    # Format and print table to console
    table = Table(
        title="Evaluation Summary",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Metric Name", style="cyan")
    table.add_column("Property", style="yellow")
    table.add_column("Value", style="green", justify="right")
    
    for sm in summary_metrics:
        table.add_row(sm["metric_name"], "mean_score", f"{sm['mean_score']:.4f}")
        
    console.print("\n", table, "\n")
    
    # Print per-case details
    console.print("[bold yellow]Per-Case Explanations:[/bold yellow]")
    for c_res in results_cases:
        console.print(f"\n[bold cyan]Case: {c_res['eval_case_id']}[/bold cyan]")
        for m_name, grade in c_res["metrics"].items():
            console.print(f"  [bold]{m_name}:[/bold] [green]Score: {grade['score']}[/green]")
            console.print(f"    [dim]Reason: {grade['explanation']}[/dim]")
            
    console.print(f"\n[green]Saved full results to {json_output_path}[/green]")
    console.print(f"[green]Saved HTML results to {html_output_path}[/green]")

if __name__ == "__main__":
    main()
