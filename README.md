# GCP → AWS Terraform Converter

An **agentic AI application** built with **LangGraph** that automatically converts
Google Cloud Platform (GCP) Infrastructure-as-Code into AWS Terraform scripts.
Supports any LLM provider — plug in your own API key.

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Pipeline                           │
│                                                                 │
│  [Scanner] → [Analyzer] → [Converter] → [PostProcessor]        │
│                                    ↓                            │
│                            [Writer] → [Reporter]               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Recursive directory scanning** — walks all folders and subfolders automatically
- **Multi-provider LLM support** — OpenAI, Anthropic, Google Gemini, Groq, Ollama (local), Azure
- **Intelligent resource mapping** — 25+ GCP → AWS resource type conversions
- **Agentic pipeline** — 6 specialised agents chained via LangGraph
- **Dependency-aware** — builds a resource dependency map before converting
- **Full output** — generates `provider.tf`, `variables.tf`, `outputs.tf`, `backend.tf`, `README.md`
- **Error isolation** — one failing file doesn't stop the rest
- **Dry-run scan** — preview discovered files before spending LLM tokens

---

## GCP → AWS Resource Mapping

| GCP Resource | AWS Equivalent |
|---|---|
| `google_compute_instance` | `aws_instance` |
| `google_compute_network` | `aws_vpc` |
| `google_compute_subnetwork` | `aws_subnet` |
| `google_compute_firewall` | `aws_security_group` |
| `google_compute_router` | `aws_route_table` / `aws_internet_gateway` |
| `google_container_cluster` | `aws_eks_cluster` |
| `google_container_node_pool` | `aws_eks_node_group` |
| `google_sql_database_instance` | `aws_db_instance` (RDS) |
| `google_storage_bucket` | `aws_s3_bucket` |
| `google_bigquery_dataset` | `aws_glue_catalog_database` |
| `google_pubsub_topic` | `aws_sns_topic` |
| `google_pubsub_subscription` | `aws_sqs_queue` |
| `google_cloudfunctions_function` | `aws_lambda_function` |
| `google_cloud_run_service` | `aws_ecs_service` (Fargate) |
| `google_iam_member` | `aws_iam_role_policy_attachment` |
| `google_kms_key_ring` / `crypto_key` | `aws_kms_key` |
| `google_secret_manager_secret` | `aws_secretsmanager_secret` |
| `google_dns_managed_zone` | `aws_route53_zone` |
| `google_redis_instance` | `aws_elasticache_replication_group` |
| `google_artifact_registry_repository` | `aws_ecr_repository` |
| `google_monitoring_alert_policy` | `aws_cloudwatch_metric_alarm` |
| `google_logging_metric` | `aws_cloudwatch_log_metric_filter` |

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/your-org/gcp-to-aws-converter
cd gcp-to-aws-converter

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your API key
cp .env.example .env
# Edit .env and add your key
```

---

## Usage

### Basic conversion (OpenAI)

```bash
python main.py convert \
  --source ./my-gcp-infra \
  --output ./aws-terraform \
  --provider openai \
  --api-key sk-...
```

### Using Anthropic Claude

```bash
python main.py convert \
  --source ./my-gcp-infra \
  --output ./aws-terraform \
  --provider anthropic \
  --model claude-3-5-sonnet-20241022
```

### Using Google Gemini

```bash
python main.py convert \
  --source ./my-gcp-infra \
  --output ./aws-terraform \
  --provider google \
  --model gemini-1.5-pro
```

### Using Groq (fast & free tier)

```bash
python main.py convert \
  --source ./my-gcp-infra \
  --output ./aws-terraform \
  --provider groq \
  --model llama3-70b-8192
```

### Using local Ollama (no API key)

```bash
# Start Ollama first: ollama run codellama:13b
python main.py convert \
  --source ./my-gcp-infra \
  --output ./aws-terraform \
  --provider ollama \
  --model codellama:13b
```

### Dry-run scan (no LLM calls)

```bash
python main.py scan --source ./my-gcp-infra
```

### List all supported providers

```bash
python main.py providers
```

---

## Supported Providers & Models

| Provider | `--provider` | Default Model | Env Var |
|---|---|---|---|
| OpenAI | `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |
| Google Gemini | `google` | `gemini-1.5-pro` | `GOOGLE_API_KEY` |
| Groq | `groq` | `llama3-70b-8192` | `GROQ_API_KEY` |
| Ollama (local) | `ollama` | `codellama:13b` | _(none)_ |
| Azure OpenAI | `azure` | `gpt-4o` | `AZURE_OPENAI_API_KEY` |

You can override the model with `--model <model-id>` for any provider.

---

## Output Structure

```
aws-terraform/
├── provider.tf           # AWS provider + terraform version constraints
├── variables.tf          # All input variables
├── outputs.tf            # Key output values
├── backend.tf            # Remote state config (commented template)
├── README.md             # Auto-generated migration notes
│
├── main_aws.tf           # Converted from main.tf
├── gke-cloudsql_aws.tf   # Converted from gke-cloudsql.tf
└── subdir/
    └── networking_aws.tf # Directory structure is preserved
```

---

## LangGraph Pipeline — Agent Roles

| # | Agent | LLM? | Role |
|---|---|---|---|
| 1 | **Scanner** | No | Walks all dirs/subdirs, reads `.tf` `.yaml` `.json` `.hcl` files |
| 2 | **Analyzer** | Yes | Understands GCP resources, builds dependency map, plans conversion |
| 3 | **Converter** | Yes | Converts each file to AWS Terraform HCL |
| 4 | **PostProcessor** | Yes | Generates `provider.tf`, `variables.tf`, `outputs.tf` |
| 5 | **Writer** | No | Persists all generated files to output directory |
| 6 | **Reporter** | No | Produces final summary report |

---

## Using as a Python Library

```python
from src.graph.state import ConversionState
from src.graph.pipeline import pipeline

state = ConversionState(
    source_dir="/path/to/gcp-infra",
    output_dir="/path/to/aws-output",
    provider="anthropic",
    model="claude-3-5-sonnet-20241022",
    api_key="sk-ant-...",
)

result = pipeline.invoke(state)

print(result.conversion_report)
print(f"Converted {len(result.converted_files)} files")
```

---

## After Conversion

```bash
cd aws-terraform

# 1. Review and update variables
nano variables.tf

# 2. Configure remote state (recommended)
nano backend.tf

# 3. Initialise Terraform
terraform init

# 4. Preview changes
terraform plan

# 5. Apply
terraform apply
```

> **Important**: Always review generated IAM policies for least-privilege compliance before applying to production.

---

## Architecture

```
main.py (CLI)
  └── src/graph/pipeline.py  (LangGraph StateGraph)
        ├── src/agents/scanner.py        Pure Python
        ├── src/agents/analyzer.py       LLM (analysis + plan)
        ├── src/agents/converter.py      LLM (per-file conversion)
        ├── src/agents/postprocessor.py  LLM (supporting files)
        ├── src/agents/writer.py         Pure Python
        └── src/agents/reporter.py       Pure Python

  └── src/llm/factory.py     (Multi-provider LLM factory)
  └── src/graph/state.py     (Pydantic shared state)
```

---

## License

MIT
