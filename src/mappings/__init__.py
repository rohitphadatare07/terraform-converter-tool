"""
Resource Mapping Registry
==========================
Defines the cloud resource type mappings for every conversion direction.

Structure:
    MAPPINGS[direction_key] = {
        "source_resource_type": {
            "target": "target_resource_type",
            "notes": "migration note shown in comments",
            "complexity": "simple|moderate|complex",
        }
    }

The LLM uses these mappings in its system prompt so it has
explicit, accurate guidance rather than relying on training data alone.
"""
from __future__ import annotations
from typing import Dict, Any

# Type alias for a single resource mapping entry
MappingEntry = Dict[str, str]
MappingTable = Dict[str, MappingEntry]


# ── GCP → AWS ──────────────────────────────────────────────────────────────
GCP_TO_AWS: MappingTable = {
    "google_compute_instance":          {"target": "aws_instance",                          "complexity": "moderate", "notes": "Map machine_type to instance_type; use AMI ID for boot disk image"},
    "google_compute_network":           {"target": "aws_vpc",                               "complexity": "simple",   "notes": "Set enable_dns_support=true, enable_dns_hostnames=true"},
    "google_compute_subnetwork":        {"target": "aws_subnet",                            "complexity": "simple",   "notes": "Map ip_cidr_range to cidr_block; add availability_zone"},
    "google_compute_firewall":          {"target": "aws_security_group",                    "complexity": "moderate", "notes": "Separate ingress/egress rules into aws_security_group_rule resources"},
    "google_compute_router":            {"target": "aws_route_table",                       "complexity": "moderate", "notes": "Also create aws_internet_gateway and aws_route_table_association"},
    "google_compute_router_nat":        {"target": "aws_nat_gateway",                       "complexity": "moderate", "notes": "Requires aws_eip for the NAT gateway"},
    "google_compute_global_address":    {"target": "aws_eip",                               "complexity": "simple",   "notes": "Use aws_lb for load balancer IPs"},
    "google_compute_instance_group":    {"target": "aws_autoscaling_group",                 "complexity": "complex",  "notes": "Create aws_launch_template first"},
    "google_compute_backend_service":   {"target": "aws_lb_target_group",                   "complexity": "moderate", "notes": "Pair with aws_lb_listener_rule"},
    "google_compute_url_map":           {"target": "aws_lb_listener",                       "complexity": "complex",  "notes": "Map path rules to listener rules"},
    "google_container_cluster":         {"target": "aws_eks_cluster",                       "complexity": "complex",  "notes": "Also create aws_eks_node_group, IAM roles, and VPC config"},
    "google_container_node_pool":       {"target": "aws_eks_node_group",                    "complexity": "moderate", "notes": "Map machine_type to instance_types list"},
    "google_sql_database_instance":     {"target": "aws_db_instance",                       "complexity": "moderate", "notes": "Map tier to instance_class; use db_subnet_group_name"},
    "google_sql_database":              {"target": "aws_db_instance",                       "complexity": "simple",   "notes": "Set db_name parameter on the aws_db_instance"},
    "google_storage_bucket":            {"target": "aws_s3_bucket",                         "complexity": "simple",   "notes": "Add aws_s3_bucket_versioning and aws_s3_bucket_lifecycle_configuration"},
    "google_bigquery_dataset":          {"target": "aws_glue_catalog_database",             "complexity": "complex",  "notes": "Use Athena + Glue for BigQuery equivalent; consider Redshift for DWH"},
    "google_bigquery_table":            {"target": "aws_glue_catalog_table",                "complexity": "complex",  "notes": "Map schema to Glue table schema format"},
    "google_pubsub_topic":              {"target": "aws_sns_topic",                         "complexity": "simple",   "notes": "SNS is pub/sub; use SQS for queuing"},
    "google_pubsub_subscription":       {"target": "aws_sqs_queue",                         "complexity": "moderate", "notes": "Add aws_sns_topic_subscription to connect SNS to SQS"},
    "google_cloudfunctions_function":   {"target": "aws_lambda_function",                   "complexity": "moderate", "notes": "Map runtime names; create IAM role; use S3 for source code"},
    "google_cloud_run_service":         {"target": "aws_ecs_service",                       "complexity": "complex",  "notes": "Use Fargate launch type; create task definition, ECS cluster, ALB"},
    "google_iam_member":                {"target": "aws_iam_role_policy_attachment",        "complexity": "moderate", "notes": "Map GCP roles to AWS managed policies"},
    "google_project_iam_binding":       {"target": "aws_iam_policy",                        "complexity": "moderate", "notes": "Create inline policy; map GCP roles to AWS actions"},
    "google_service_account":           {"target": "aws_iam_role",                          "complexity": "moderate", "notes": "Add assume_role_policy for the appropriate AWS service"},
    "google_kms_key_ring":              {"target": "aws_kms_key",                           "complexity": "simple",   "notes": "KMS key ring maps to a KMS key; add aws_kms_alias"},
    "google_kms_crypto_key":            {"target": "aws_kms_alias",                         "complexity": "simple",   "notes": "Rotation period maps to enable_key_rotation"},
    "google_secret_manager_secret":     {"target": "aws_secretsmanager_secret",             "complexity": "simple",   "notes": "Add aws_secretsmanager_secret_version for the value"},
    "google_dns_managed_zone":          {"target": "aws_route53_zone",                      "complexity": "simple",   "notes": "Set private_zone=true for private zones"},
    "google_dns_record_set":            {"target": "aws_route53_record",                    "complexity": "simple",   "notes": "Map type, ttl, rrdatas directly"},
    "google_redis_instance":            {"target": "aws_elasticache_replication_group",     "complexity": "moderate", "notes": "Map tier to node_type; set engine=redis"},
    "google_artifact_registry_repository": {"target": "aws_ecr_repository",                "complexity": "simple",   "notes": "Map DOCKER format to ECR; add lifecycle policy"},
    "google_logging_metric":            {"target": "aws_cloudwatch_log_metric_filter",      "complexity": "moderate", "notes": "Map filter pattern syntax"},
    "google_monitoring_alert_policy":   {"target": "aws_cloudwatch_metric_alarm",           "complexity": "moderate", "notes": "Map conditions to CloudWatch alarm metrics"},
    "google_spanner_instance":          {"target": "aws_dynamodb_table",                    "complexity": "complex",  "notes": "No direct equivalent; DynamoDB for NoSQL or RDS Aurora for relational"},
    "google_filestore_instance":        {"target": "aws_efs_file_system",                   "complexity": "moderate", "notes": "Add aws_efs_mount_target for each subnet"},
    "google_composer_environment":      {"target": "aws_mwaa_environment",                  "complexity": "complex",  "notes": "Managed Airflow; requires S3 bucket for DAGs"},
}

# ── AWS → GCP ──────────────────────────────────────────────────────────────
AWS_TO_GCP: MappingTable = {
    "aws_instance":                     {"target": "google_compute_instance",               "complexity": "moderate", "notes": "Map instance_type to machine_type; use GCP image for boot disk"},
    "aws_vpc":                          {"target": "google_compute_network",                "complexity": "simple",   "notes": "Set auto_create_subnetworks=false"},
    "aws_subnet":                       {"target": "google_compute_subnetwork",             "complexity": "simple",   "notes": "Map cidr_block to ip_cidr_range"},
    "aws_security_group":               {"target": "google_compute_firewall",               "complexity": "moderate", "notes": "Create one firewall rule per ingress/egress block"},
    "aws_route_table":                  {"target": "google_compute_router",                 "complexity": "moderate", "notes": "GCP uses Cloud Router + routes instead of route tables"},
    "aws_nat_gateway":                  {"target": "google_compute_router_nat",             "complexity": "moderate", "notes": "Attach to google_compute_router"},
    "aws_eks_cluster":                  {"target": "google_container_cluster",              "complexity": "complex",  "notes": "Map node groups to google_container_node_pool"},
    "aws_eks_node_group":               {"target": "google_container_node_pool",            "complexity": "moderate", "notes": "Map instance_types to machine_type"},
    "aws_db_instance":                  {"target": "google_sql_database_instance",          "complexity": "moderate", "notes": "Map instance_class to tier; set database_version"},
    "aws_s3_bucket":                    {"target": "google_storage_bucket",                 "complexity": "simple",   "notes": "Map region to location; add uniform_bucket_level_access=true"},
    "aws_sns_topic":                    {"target": "google_pubsub_topic",                   "complexity": "simple",   "notes": "Add schema_settings if using Avro"},
    "aws_sqs_queue":                    {"target": "google_pubsub_subscription",            "complexity": "moderate", "notes": "Create google_pubsub_topic first"},
    "aws_lambda_function":              {"target": "google_cloudfunctions_function",        "complexity": "moderate", "notes": "Map runtime names; use GCS bucket for source"},
    "aws_ecs_service":                  {"target": "google_cloud_run_service",              "complexity": "complex",  "notes": "Fargate maps well to Cloud Run; map task definition to container spec"},
    "aws_iam_role":                     {"target": "google_service_account",               "complexity": "moderate", "notes": "Map assume_role_policy to GCP workload identity"},
    "aws_iam_policy":                   {"target": "google_project_iam_binding",            "complexity": "moderate", "notes": "Map AWS actions to GCP roles"},
    "aws_kms_key":                      {"target": "google_kms_crypto_key",                "complexity": "simple",   "notes": "Create google_kms_key_ring first"},
    "aws_secretsmanager_secret":        {"target": "google_secret_manager_secret",         "complexity": "simple",   "notes": "Add google_secret_manager_secret_version for value"},
    "aws_route53_zone":                 {"target": "google_dns_managed_zone",              "complexity": "simple",   "notes": "Map private_zone to visibility"},
    "aws_route53_record":               {"target": "google_dns_record_set",                "complexity": "simple",   "notes": "Map records list to rrdatas"},
    "aws_elasticache_replication_group":{"target": "google_redis_instance",                "complexity": "moderate", "notes": "Map node_type to tier"},
    "aws_ecr_repository":               {"target": "google_artifact_registry_repository",  "complexity": "simple",   "notes": "Set format=DOCKER"},
    "aws_cloudwatch_metric_alarm":      {"target": "google_monitoring_alert_policy",       "complexity": "moderate", "notes": "Map metric namespace and conditions"},
    "aws_cloudwatch_log_metric_filter": {"target": "google_logging_metric",               "complexity": "moderate", "notes": "Map filter pattern to GCP logging filter syntax"},
    "aws_dynamodb_table":               {"target": "google_spanner_instance",              "complexity": "complex",  "notes": "Spanner for global ACID; Firestore for document model"},
    "aws_efs_file_system":              {"target": "google_filestore_instance",            "complexity": "moderate", "notes": "Map performance_mode to tier"},
    "aws_alb":                          {"target": "google_compute_global_forwarding_rule", "complexity": "complex",  "notes": "Also create backend service, URL map, target proxy"},
    "aws_autoscaling_group":            {"target": "google_compute_instance_group_manager", "complexity": "complex",  "notes": "Create instance template first"},
}

# ── GCP → Azure ────────────────────────────────────────────────────────────
GCP_TO_AZURE: MappingTable = {
    "google_compute_instance":          {"target": "azurerm_linux_virtual_machine",         "complexity": "moderate", "notes": "Map machine_type to size; specify resource_group_name"},
    "google_compute_network":           {"target": "azurerm_virtual_network",               "complexity": "simple",   "notes": "Specify address_space as CIDR list"},
    "google_compute_subnetwork":        {"target": "azurerm_subnet",                        "complexity": "simple",   "notes": "Map ip_cidr_range to address_prefixes"},
    "google_compute_firewall":          {"target": "azurerm_network_security_group",        "complexity": "moderate", "notes": "Map allow/deny rules to security_rule blocks"},
    "google_compute_router_nat":        {"target": "azurerm_nat_gateway",                   "complexity": "moderate", "notes": "Requires azurerm_public_ip and subnet association"},
    "google_container_cluster":         {"target": "azurerm_kubernetes_cluster",            "complexity": "complex",  "notes": "Map node pools to default_node_pool and azurerm_kubernetes_cluster_node_pool"},
    "google_container_node_pool":       {"target": "azurerm_kubernetes_cluster_node_pool",  "complexity": "moderate", "notes": "Map machine_type to vm_size"},
    "google_sql_database_instance":     {"target": "azurerm_postgresql_flexible_server",    "complexity": "moderate", "notes": "Map database_version; choose MySQL→azurerm_mysql_flexible_server"},
    "google_storage_bucket":            {"target": "azurerm_storage_account",               "complexity": "moderate", "notes": "Create azurerm_storage_container inside the account"},
    "google_bigquery_dataset":          {"target": "azurerm_synapse_workspace",             "complexity": "complex",  "notes": "Synapse Analytics for DWH; use Data Lake Storage Gen2"},
    "google_pubsub_topic":              {"target": "azurerm_servicebus_topic",              "complexity": "simple",   "notes": "Create azurerm_servicebus_namespace first"},
    "google_pubsub_subscription":       {"target": "azurerm_servicebus_subscription",       "complexity": "simple",   "notes": "Attach to azurerm_servicebus_topic"},
    "google_cloudfunctions_function":   {"target": "azurerm_function_app",                  "complexity": "moderate", "notes": "Create storage account and app service plan first"},
    "google_cloud_run_service":         {"target": "azurerm_container_app",                 "complexity": "complex",  "notes": "Use Container Apps Environment; map concurrency to scale rules"},
    "google_service_account":           {"target": "azurerm_user_assigned_identity",        "complexity": "moderate", "notes": "Use azurerm_role_assignment to grant permissions"},
    "google_iam_member":                {"target": "azurerm_role_assignment",               "complexity": "moderate", "notes": "Map GCP roles to Azure built-in role definition IDs"},
    "google_kms_crypto_key":            {"target": "azurerm_key_vault_key",                 "complexity": "moderate", "notes": "Create azurerm_key_vault first; set purge_protection_enabled=true"},
    "google_secret_manager_secret":     {"target": "azurerm_key_vault_secret",              "complexity": "simple",   "notes": "Store in azurerm_key_vault"},
    "google_dns_managed_zone":          {"target": "azurerm_dns_zone",                      "complexity": "simple",   "notes": "Private zones use azurerm_private_dns_zone"},
    "google_dns_record_set":            {"target": "azurerm_dns_a_record",                  "complexity": "simple",   "notes": "Choose record type resource: azurerm_dns_cname_record, etc."},
    "google_redis_instance":            {"target": "azurerm_redis_cache",                   "complexity": "simple",   "notes": "Map tier to sku_name: Basic/Standard/Premium"},
    "google_artifact_registry_repository": {"target": "azurerm_container_registry",        "complexity": "simple",   "notes": "Set sku=Standard or Premium for geo-replication"},
    "google_monitoring_alert_policy":   {"target": "azurerm_monitor_metric_alert",          "complexity": "moderate", "notes": "Map conditions to criteria blocks"},
    "google_logging_metric":            {"target": "azurerm_monitor_diagnostic_setting",    "complexity": "moderate", "notes": "Send to Log Analytics workspace"},
}

# ── Azure → GCP ────────────────────────────────────────────────────────────
AZURE_TO_GCP: MappingTable = {
    "azurerm_linux_virtual_machine":    {"target": "google_compute_instance",               "complexity": "moderate", "notes": "Map size to machine_type; choose GCP boot image"},
    "azurerm_virtual_network":          {"target": "google_compute_network",                "complexity": "simple",   "notes": "Set auto_create_subnetworks=false"},
    "azurerm_subnet":                   {"target": "google_compute_subnetwork",             "complexity": "simple",   "notes": "Map address_prefixes[0] to ip_cidr_range"},
    "azurerm_network_security_group":   {"target": "google_compute_firewall",               "complexity": "moderate", "notes": "One firewall per security_rule block"},
    "azurerm_kubernetes_cluster":       {"target": "google_container_cluster",              "complexity": "complex",  "notes": "Map default_node_pool to google_container_node_pool"},
    "azurerm_kubernetes_cluster_node_pool": {"target": "google_container_node_pool",       "complexity": "moderate", "notes": "Map vm_size to machine_type"},
    "azurerm_postgresql_flexible_server": {"target": "google_sql_database_instance",       "complexity": "moderate", "notes": "Set database_version=POSTGRES_*"},
    "azurerm_mysql_flexible_server":    {"target": "google_sql_database_instance",         "complexity": "moderate", "notes": "Set database_version=MYSQL_8_0"},
    "azurerm_storage_account":          {"target": "google_storage_bucket",                "complexity": "moderate", "notes": "Map account_tier to storage class"},
    "azurerm_servicebus_topic":         {"target": "google_pubsub_topic",                  "complexity": "simple",   "notes": "Pub/Sub is the GCP equivalent"},
    "azurerm_servicebus_subscription":  {"target": "google_pubsub_subscription",           "complexity": "simple",   "notes": "Attach to google_pubsub_topic"},
    "azurerm_function_app":             {"target": "google_cloudfunctions_function",        "complexity": "moderate", "notes": "Use GCS bucket for source; map runtime"},
    "azurerm_container_app":            {"target": "google_cloud_run_service",              "complexity": "complex",  "notes": "Cloud Run is the closest equivalent"},
    "azurerm_user_assigned_identity":   {"target": "google_service_account",               "complexity": "moderate", "notes": "Use workload identity for GKE"},
    "azurerm_role_assignment":          {"target": "google_project_iam_binding",           "complexity": "moderate", "notes": "Map Azure role to GCP role"},
    "azurerm_key_vault_key":            {"target": "google_kms_crypto_key",                "complexity": "moderate", "notes": "Create google_kms_key_ring first"},
    "azurerm_key_vault_secret":         {"target": "google_secret_manager_secret",         "complexity": "simple",   "notes": "Add google_secret_manager_secret_version"},
    "azurerm_dns_zone":                 {"target": "google_dns_managed_zone",              "complexity": "simple",   "notes": "Set visibility=public or private"},
    "azurerm_redis_cache":              {"target": "google_redis_instance",                "complexity": "simple",   "notes": "Map sku_name to tier"},
    "azurerm_container_registry":       {"target": "google_artifact_registry_repository",  "complexity": "simple",   "notes": "Set format=DOCKER"},
    "azurerm_monitor_metric_alert":     {"target": "google_monitoring_alert_policy",       "complexity": "moderate", "notes": "Map criteria blocks to conditions"},
    "azurerm_synapse_workspace":        {"target": "google_bigquery_dataset",              "complexity": "complex",  "notes": "BigQuery for DWH; map to google_bigquery_table for schemas"},
    "azurerm_nat_gateway":              {"target": "google_compute_router_nat",            "complexity": "moderate", "notes": "Attach to google_compute_router"},
}

# ── Azure → AWS ────────────────────────────────────────────────────────────
AZURE_TO_AWS: MappingTable = {
    "azurerm_linux_virtual_machine":    {"target": "aws_instance",                         "complexity": "moderate", "notes": "Map size to instance_type; use AMI for image"},
    "azurerm_virtual_network":          {"target": "aws_vpc",                              "complexity": "simple",   "notes": "Map address_space[0] to cidr_block"},
    "azurerm_subnet":                   {"target": "aws_subnet",                           "complexity": "simple",   "notes": "Map address_prefixes[0] to cidr_block"},
    "azurerm_network_security_group":   {"target": "aws_security_group",                   "complexity": "moderate", "notes": "Map security_rule blocks to ingress/egress"},
    "azurerm_kubernetes_cluster":       {"target": "aws_eks_cluster",                      "complexity": "complex",  "notes": "Map default_node_pool to aws_eks_node_group"},
    "azurerm_kubernetes_cluster_node_pool": {"target": "aws_eks_node_group",              "complexity": "moderate", "notes": "Map vm_size to instance_types"},
    "azurerm_postgresql_flexible_server": {"target": "aws_db_instance",                   "complexity": "moderate", "notes": "Set engine=postgres; map sku to instance_class"},
    "azurerm_mysql_flexible_server":    {"target": "aws_db_instance",                     "complexity": "moderate", "notes": "Set engine=mysql"},
    "azurerm_storage_account":          {"target": "aws_s3_bucket",                       "complexity": "moderate", "notes": "Create separate S3 bucket for each container"},
    "azurerm_servicebus_topic":         {"target": "aws_sns_topic",                       "complexity": "simple",   "notes": "SNS is the closest pub/sub equivalent"},
    "azurerm_servicebus_subscription":  {"target": "aws_sqs_queue",                       "complexity": "moderate", "notes": "Add aws_sns_topic_subscription"},
    "azurerm_function_app":             {"target": "aws_lambda_function",                  "complexity": "moderate", "notes": "Map runtime; use S3 for code; create IAM role"},
    "azurerm_container_app":            {"target": "aws_ecs_service",                     "complexity": "complex",  "notes": "Use Fargate; create task definition and cluster"},
    "azurerm_user_assigned_identity":   {"target": "aws_iam_role",                        "complexity": "moderate", "notes": "Add assume_role_policy for the service"},
    "azurerm_role_assignment":          {"target": "aws_iam_role_policy_attachment",      "complexity": "moderate", "notes": "Map Azure role to AWS managed policy ARN"},
    "azurerm_key_vault_key":            {"target": "aws_kms_key",                         "complexity": "simple",   "notes": "Add aws_kms_alias for the key"},
    "azurerm_key_vault_secret":         {"target": "aws_secretsmanager_secret",           "complexity": "simple",   "notes": "Add aws_secretsmanager_secret_version"},
    "azurerm_dns_zone":                 {"target": "aws_route53_zone",                    "complexity": "simple",   "notes": "Set private_zone based on zone type"},
    "azurerm_redis_cache":              {"target": "aws_elasticache_replication_group",   "complexity": "moderate", "notes": "Set engine=redis; map sku to node_type"},
    "azurerm_container_registry":       {"target": "aws_ecr_repository",                  "complexity": "simple",   "notes": "Add lifecycle policy for image cleanup"},
    "azurerm_monitor_metric_alert":     {"target": "aws_cloudwatch_metric_alarm",         "complexity": "moderate", "notes": "Map criteria to CloudWatch metric dimensions"},
    "azurerm_nat_gateway":              {"target": "aws_nat_gateway",                     "complexity": "simple",   "notes": "Requires aws_eip; associate with subnet"},
    "azurerm_synapse_workspace":        {"target": "aws_redshift_cluster",                "complexity": "complex",  "notes": "Redshift for DWH; use Glue + Athena for serverless"},
    "azurerm_application_gateway":      {"target": "aws_alb",                             "complexity": "complex",  "notes": "Map routing rules to listener rules and target groups"},
}

# ── AWS → Azure ────────────────────────────────────────────────────────────
AWS_TO_AZURE: MappingTable = {
    "aws_instance":                     {"target": "azurerm_linux_virtual_machine",        "complexity": "moderate", "notes": "Map instance_type to size; create NIC and OS disk"},
    "aws_vpc":                          {"target": "azurerm_virtual_network",              "complexity": "simple",   "notes": "Map cidr_block to address_space"},
    "aws_subnet":                       {"target": "azurerm_subnet",                       "complexity": "simple",   "notes": "Map cidr_block to address_prefixes"},
    "aws_security_group":               {"target": "azurerm_network_security_group",       "complexity": "moderate", "notes": "Map ingress/egress blocks to security_rule blocks"},
    "aws_eks_cluster":                  {"target": "azurerm_kubernetes_cluster",           "complexity": "complex",  "notes": "Map node groups to node_pool resources"},
    "aws_eks_node_group":               {"target": "azurerm_kubernetes_cluster_node_pool", "complexity": "moderate", "notes": "Map instance_types[0] to vm_size"},
    "aws_db_instance":                  {"target": "azurerm_postgresql_flexible_server",   "complexity": "moderate", "notes": "Choose MySQL→azurerm_mysql_flexible_server if engine=mysql"},
    "aws_s3_bucket":                    {"target": "azurerm_storage_account",              "complexity": "moderate", "notes": "Create azurerm_storage_container for each logical bucket"},
    "aws_sns_topic":                    {"target": "azurerm_servicebus_topic",             "complexity": "moderate", "notes": "Create azurerm_servicebus_namespace first"},
    "aws_sqs_queue":                    {"target": "azurerm_servicebus_queue",             "complexity": "simple",   "notes": "Map visibility_timeout to lock_duration"},
    "aws_lambda_function":              {"target": "azurerm_function_app",                 "complexity": "moderate", "notes": "Map runtime; create storage account and service plan"},
    "aws_ecs_service":                  {"target": "azurerm_container_app",                "complexity": "complex",  "notes": "Use Container Apps; map task definition to template"},
    "aws_iam_role":                     {"target": "azurerm_user_assigned_identity",       "complexity": "moderate", "notes": "Use azurerm_role_assignment to grant access"},
    "aws_iam_policy":                   {"target": "azurerm_role_definition",              "complexity": "moderate", "notes": "Map actions to Azure permission strings"},
    "aws_kms_key":                      {"target": "azurerm_key_vault_key",                "complexity": "moderate", "notes": "Create azurerm_key_vault first"},
    "aws_secretsmanager_secret":        {"target": "azurerm_key_vault_secret",             "complexity": "simple",   "notes": "Store in azurerm_key_vault"},
    "aws_route53_zone":                 {"target": "azurerm_dns_zone",                     "complexity": "simple",   "notes": "Private zones use azurerm_private_dns_zone"},
    "aws_route53_record":               {"target": "azurerm_dns_a_record",                 "complexity": "simple",   "notes": "Choose specific record type resource"},
    "aws_elasticache_replication_group":{"target": "azurerm_redis_cache",                  "complexity": "moderate", "notes": "Map node_type to sku_name"},
    "aws_ecr_repository":               {"target": "azurerm_container_registry",           "complexity": "simple",   "notes": "Set sku=Standard; enable admin_enabled if needed"},
    "aws_cloudwatch_metric_alarm":      {"target": "azurerm_monitor_metric_alert",         "complexity": "moderate", "notes": "Map metric_name to criteria.metric_name"},
    "aws_nat_gateway":                  {"target": "azurerm_nat_gateway",                  "complexity": "simple",   "notes": "Create azurerm_public_ip and associate"},
    "aws_alb":                          {"target": "azurerm_application_gateway",          "complexity": "complex",  "notes": "Map listeners and target groups to routing rules"},
    "aws_redshift_cluster":             {"target": "azurerm_synapse_workspace",            "complexity": "complex",  "notes": "Use Synapse Analytics + dedicated SQL pool"},
    "aws_autoscaling_group":            {"target": "azurerm_virtual_machine_scale_set",    "complexity": "complex",  "notes": "Map launch_template to azurerm_linux_virtual_machine properties"},
    "aws_efs_file_system":              {"target": "azurerm_storage_share",                "complexity": "moderate", "notes": "Use Azure Files (SMB/NFS) in a storage account"},
}


# ── Master registry ────────────────────────────────────────────────────────

ALL_MAPPINGS: Dict[str, MappingTable] = {
    "gcp-aws":   GCP_TO_AWS,
    "aws-gcp":   AWS_TO_GCP,
    "gcp-azure": GCP_TO_AZURE,
    "azure-gcp": AZURE_TO_GCP,
    "azure-aws": AZURE_TO_AWS,
    "aws-azure": AWS_TO_AZURE,
}


def get_mapping(direction_key: str) -> MappingTable:
    """Return the resource mapping table for a given direction key."""
    if direction_key not in ALL_MAPPINGS:
        raise ValueError(f"No mapping table found for direction '{direction_key}'")
    return ALL_MAPPINGS[direction_key]


def mapping_to_prompt_text(direction_key: str) -> str:
    """
    Format the mapping table as a concise prompt snippet for the LLM.
    Returns lines like:
        aws_instance → google_compute_instance  [moderate] Map machine_type...
    """
    table = get_mapping(direction_key)
    lines = []
    for src, entry in table.items():
        tgt = entry["target"]
        cplx = entry.get("complexity", "")
        notes = entry.get("notes", "")
        lines.append(f"  {src:<50} → {tgt:<45} [{cplx}] {notes}")
    return "\n".join(lines)
