import pulumi
import pulumi_gcp as gcp


def enable_resource_manager_api(project: str, provider: gcp.Provider) -> gcp.projects.Service:
    """
    Enables the Cloud Resource Manager API for the specified GCP project.

    This API is required for project-level operations, IAM policy management,
    and access to project metadata. Many other Google Cloud services depend
    on it for permissions and resource hierarchy handling.
    """

    return gcp.projects.Service(
        "enable-cloudresourcemanager-api",
        project=project,
        service="cloudresourcemanager.googleapis.com",
        disable_on_destroy=False,
        opts=pulumi.ResourceOptions(provider=provider),
    )
