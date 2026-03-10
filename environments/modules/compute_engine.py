import pulumi_gcp as gcp
import pulumi


def enable_compute_engine_api(project: str, provider: gcp.Provider) -> gcp.projects.Service:
    """
    Enables the Compute Engine API for the specified GCP project.

    Required because several services (including Cloud Run and Artifact Registry)
    depend on Compute Engine infrastructure such as networking and regional
    resources.
    """

    return gcp.projects.Service(
        "enable-compute-engine-api",
        project=project,
        service="compute.googleapis.com",
        disable_on_destroy=False,
        opts=pulumi.ResourceOptions(provider=provider),
    )
