import pulumi
import pulumi_gcp as gcp
from typing import Any, Mapping, Optional


def deploy_public_cloud_run(
    base_name: str,
    image: Any,  # expects image["image_name"] and image["repo_digest"] (Pulumi Outputs)
    env: str,  # typically "production"
    region: str,  # e.g. "europe-west1"
    provider: gcp.Provider,
    env_vars: Optional[Mapping[str, str]] = None,
    max_instances: int = 100,
    cpu: str = "1",
    memory: str = "512Mi",
    gpu: Optional[int] = None,
    gpu_type: Optional[str] = None,
) -> pulumi.Output[str]:
    """
    Deploy a publicly invokable Cloud Run v2 service (production):
      1) Enable required Google Cloud APIs (Cloud Run + IAM)
      2) Create a dedicated service account and grant logging permissions
      3) Create the Cloud Run v2 service using the provided image (GPU + sizing + concurrency)
      4) Grant public invoker access (allUsers)
      5) Return the service HTTPS URL
    """
    env_vars = dict(env_vars or {})  # Normalize optional env vars into a mutable dictionary
    has_gpu = gpu is not None and gpu > 0  # Single reusable flag for all GPU-specific configuration

    # 1) Enable required Google Cloud APIs (Cloud Run + IAM)
    enable_run_api = gcp.projects.Service(
        f"{base_name}-enable-run",
        service="run.googleapis.com",
        disable_on_destroy=False,
        opts=pulumi.ResourceOptions(provider=provider),
    )

    enable_iam_api = gcp.projects.Service(
        f"{base_name}-enable-iam",
        service="iam.googleapis.com",
        disable_on_destroy=False,
        opts=pulumi.ResourceOptions(provider=provider),
    )

    # 2) Dedicated service account for Cloud Run + minimal role(s)
    run_service_account = gcp.serviceaccount.Account(
        f"{base_name}-sa-cloud-run",
        account_id=f"{base_name}-sa-cloud-run",
        display_name=pulumi.Output.concat(base_name, " Cloud Run Service Account"),
        opts=pulumi.ResourceOptions(provider=provider, depends_on=[enable_iam_api]),
    )

    sa_log_writer = gcp.projects.IAMMember(
        f"{base_name}-sa-log-writer",
        project=provider.project,
        role="roles/logging.logWriter",
        member=run_service_account.email.apply(lambda e: f"serviceAccount:{e}"),
        opts=pulumi.ResourceOptions(provider=provider, depends_on=[run_service_account]),
    )

    # 3) Cloud Run v2 service configuration
    # DIGEST is used to force Cloud Run to create a new revision when the image changes,
    # even if the tag name (e.g. :latest) stays the same.
    #
    # GPU configuration (Cloud Run services):
    # - Request 1 GPU by setting resources.limits["nvidia.com/gpu"] = "1"
    # - Select the GPU type via template.node_selector.accelerator = "nvidia-l4"
    #   (note: it's "nvidia-l4" with a lowercase letter "l", not "nvidia-14").
    def _make_service(args):
        image_name, image_digest, sa_email = args
        digest_tail = image_digest[-71:] if image_digest else ""

        # Base environment variables always applied
        base_env_vars = {
            "NODE_ENV": env,
            "DIGEST": digest_tail,
        }

        # Merge caller-provided env vars (caller overrides base if duplicated)
        merged_env_vars = {**base_env_vars, **env_vars}

        # Resource limits
        limits = {
            "cpu": cpu,
            "memory": memory,
        }
        if has_gpu:
            limits["nvidia.com/gpu"] = str(gpu)

        # Optional GPU selector
        node_selector = (
            gcp.cloudrunv2.ServiceTemplateNodeSelectorArgs(accelerator=gpu_type)
            if (has_gpu and gpu_type)
            else None
        )

        return gcp.cloudrunv2.Service(
            f"{base_name}-service",
            name=f"{base_name}-service",
            location=region,
            ingress="INGRESS_TRAFFIC_ALL",
            deletion_protection=False,
            template=gcp.cloudrunv2.ServiceTemplateArgs(
                service_account=sa_email,
                session_affinity=True,
                # Disable GPU zonal redundancy to avoid quota requirement. Only set this for GPU services                
                gpu_zonal_redundancy_disabled=True if has_gpu else None,
                # Autoscaling
                scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(
                    min_instance_count=0,
                    max_instance_count=max_instances,
                ),
                node_selector=node_selector,
                containers=[
                    gcp.cloudrunv2.ServiceTemplateContainerArgs(
                        image=image_name,
                        envs=[
                            gcp.cloudrunv2.ServiceTemplateContainerEnvArgs(
                                name=k,
                                value=v,
                            )
                            for k, v in merged_env_vars.items()
                        ],
                        ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(
                            name="http1",
                            container_port=8080,
                        ),
                        resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                            startup_cpu_boost=True,
                            # Keep CPU allocated even when the service is idle to avoid
                            # post-idle ramp-up throttling and reduce latency spikes.
                            cpu_idle=False,
                            # Sizing
                            limits=limits,
                        ),
                    )
                ],
            ),
            opts=pulumi.ResourceOptions(
                provider=provider,
                depends_on=[enable_run_api, enable_iam_api, sa_log_writer],
            ),
        )

    service = pulumi.Output.all(
        image["image_name"],
        image["repo_digest"],
        run_service_account.email,
    ).apply(_make_service)

    # 4) Public invoker access (production)
    gcp.cloudrunv2.ServiceIamMember(
        f"{base_name}-public-invoker",
        name=service.name,
        location=region,
        role="roles/run.invoker",
        member="allUsers",
        opts=pulumi.ResourceOptions(provider=provider, depends_on=[service]),
    )

    # 5) Return public URL
    return service.uri
