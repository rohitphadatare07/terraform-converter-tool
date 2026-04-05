"""
Agent 3 – Terraform Converter
Converts each discovered GCP IaC file into AWS Terraform HCL.
Runs once per file; the LangGraph runner calls this node for each FileInfo.
"""
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.state import ConversionState, ConvertedFile
from src.llm.factory import get_llm

SYSTEM_PROMPT = """You are a senior DevOps/Cloud engineer specialising in cloud infrastructure
migration. You convert GCP (Google Cloud Platform) Infrastructure-as-Code into AWS Terraform.

Rules:
1. Output ONLY valid HCL Terraform code – no explanations, no markdown fences.
2. Replace every GCP resource with its closest AWS equivalent.
3. Preserve resource naming conventions as much as possible.
4. Use Terraform best practices: variables for repeated values, locals for computed values.
5. Add inline comments (# ...) where the mapping is non-trivial.
6. If a GCP resource has no direct AWS equivalent, create a commented stub and add a TODO.
7. Do NOT include the provider block – that is handled separately.
8. Use var.aws_region, var.aws_account_id, var.project_name as standard variables.

GCP → AWS mapping reminders:
  google_compute_instance        → aws_instance
  google_compute_network         → aws_vpc
  google_compute_subnetwork      → aws_subnet
  google_compute_firewall        → aws_security_group
  google_compute_router          → aws_route_table / aws_internet_gateway
  google_compute_global_address  → aws_eip / aws_lb
  google_container_cluster       → aws_eks_cluster
  google_container_node_pool     → aws_eks_node_group
  google_sql_database_instance   → aws_db_instance (RDS)
  google_sql_database            → aws_db_instance (database param)
  google_storage_bucket          → aws_s3_bucket
  google_bigquery_dataset        → aws_glue_catalog_database or aws_athena_*
  google_bigquery_table          → aws_glue_catalog_table
  google_pubsub_topic            → aws_sns_topic
  google_pubsub_subscription     → aws_sqs_queue + aws_sns_topic_subscription
  google_cloud_run_service       → aws_ecs_service (Fargate) or aws_lambda_function
  google_cloudfunctions_function → aws_lambda_function
  google_iam_member              → aws_iam_role_policy_attachment / aws_iam_policy
  google_project_iam_binding     → aws_iam_policy
  google_kms_key_ring            → aws_kms_key
  google_kms_crypto_key          → aws_kms_key (alias)
  google_secret_manager_secret   → aws_secretsmanager_secret
  google_dns_managed_zone        → aws_route53_zone
  google_dns_record_set          → aws_route53_record
  google_redis_instance          → aws_elasticache_replication_group
  google_artifact_registry_repo  → aws_ecr_repository
  google_logging_metric          → aws_cloudwatch_log_metric_filter
  google_monitoring_alert_policy → aws_cloudwatch_metric_alarm
  google_cloudfunctions2_function → aws_lambda_function (with eventbridge trigger)
  google_cloudfunctions_function → aws_lambda_function (with appropriate trigger based on event type)
  google_compute_disk             → aws_ebs_volume
  google_compute_image            → aws_ami (imported or from marketplace)
  google_compute_instance_group   → aws_autoscaling_group
  google_compute_instance_template → aws_launch_template
  google_compute_instance_from_template → aws_autoscaling_group with launch template
  google_compute_managed_ssl_certificate → aws_acm_certificate
  google_compute_ssl_certificate         → aws_acm_certificate
  google_compute_target_https_proxy      → aws_lb_listener (with certificate)
  google_compute_url_map                → aws_lb_listener_rule
  google_compute_backend_service        → aws_lb_target_group
  google_compute_health_check          → aws_lb_target_group health_check
  google_compute_forwarding_rule        → aws_lb_listener + aws_lb_target_group
"""

CONVERT_PROMPT = """Convert the following GCP IaC file to AWS Terraform HCL.

Source file: {relative_path}
File type: {file_type}

--- BEGIN SOURCE ---
{content}
--- END SOURCE ---

Context from overall infrastructure analysis:
{conversion_plan}

Output ONLY the converted Terraform HCL (no markdown, no backticks):
"""


def _extract_aws_resources(hcl: str):
    """Return a list of AWS resource type strings found in the HCL."""
    return list(set(re.findall(r'resource\s+"(aws_[^"]+)"', hcl)))


def _derive_output_path(relative_path: str, output_dir: str) -> str:
    """
    Mirror the source directory structure under output_dir.
    Rename files to make clear they are AWS resources.
    """
    p = Path(relative_path)
    # Keep directory structure, suffix stays .tf
    new_name = p.stem + "_aws" + ".tf"
    out = Path(output_dir) / p.parent / new_name
    return str(out)


def converter_agent(state: ConversionState) -> ConversionState:
    """
    LangGraph node: convert ALL discovered files.
    Each file is converted independently so failures are isolated.
    """
    if not state.discovered_files:
        return state

    llm = get_llm(
        provider=state.provider,
        model=state.model,
        api_key=state.api_key,
    )

    converted: list[ConvertedFile] = []
    failed: list[str] = []

    for file_info in state.discovered_files:
        try:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(
                    content=CONVERT_PROMPT.format(
                        relative_path=file_info.relative_path,
                        file_type=file_info.file_type,
                        content=file_info.content[:8000],  # safety truncation
                        conversion_plan=state.conversion_plan[:2000],
                    )
                ),
            ]

            response = llm.invoke(messages)
            aws_content = response.content.strip()

            # Strip any accidental markdown fences
            if aws_content.startswith("```"):
                parts = aws_content.split("```")
                # parts[1] contains the code
                aws_content = parts[1]
                if aws_content.startswith("hcl") or aws_content.startswith("terraform"):
                    aws_content = "\n".join(aws_content.splitlines()[1:])
                aws_content = aws_content.strip()

            output_path = _derive_output_path(
                file_info.relative_path, state.output_dir
            )
            resources = _extract_aws_resources(aws_content)

            converted.append(
                ConvertedFile(
                    source_path=file_info.path,
                    output_path=output_path,
                    aws_content=aws_content,
                    resources_converted=resources,
                )
            )

        except Exception as exc:
            failed.append(
                f"{file_info.relative_path}: {exc}"
            )

    # Use list concat (annotated with operator.add) via direct assignment
    state.converted_files = state.converted_files + converted
    state.failed_files = state.failed_files + failed
    return state
