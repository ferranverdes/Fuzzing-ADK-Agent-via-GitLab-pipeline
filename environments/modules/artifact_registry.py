import os
from typing import List, Optional, TypedDict

import pulumi
import pulumi_gcp as gcp
import pulumi_docker as docker


class BuiltImage(TypedDict):
    image_name: pulumi.Output[str]
    repo_digest: pulumi.Output[str]


def create_artifact_registry_repository(
    name: str,
    region: str,
    provider: gcp.Provider,
    depends_on: Optional[List[pulumi.Resource]] = None,
) -> gcp.artifactregistry.Repository:
    """
    Creates a Docker-compatible Artifact Registry repository in the specified region.

    This function:
    - Enables the Artifact Registry API (artifactregistry.googleapis.com).
    - Creates a DOCKER-format repository for storing container images.
    - Accepts optional depends_on resources to enforce creation order.
    """
    depends_on = depends_on or []

    # Enable the Artifact Registry API (required to manage Artifact Registry repositories)
    artifact_registry_api = gcp.projects.Service(
        f"{name}-enable-artifactregistry-api",
        service="artifactregistry.googleapis.com",
        disable_on_destroy=False,
        opts=pulumi.ResourceOptions(provider=provider),
    )

    # Create a Docker-format repository in Artifact Registry
    repository = gcp.artifactregistry.Repository(
        name,
        repository_id=name,
        format="DOCKER",
        location=region,
        description="Docker image repo for Cloud Run apps",
        opts=pulumi.ResourceOptions(
            provider=provider,
            depends_on=[artifact_registry_api, *depends_on],
        ),
    )

    return repository


def build_and_push_docker_image(
    name: str,
    local_path: str,
    project: str,
    region: str,
    repository: gcp.artifactregistry.Repository,
    sa_key_path: Optional[str] = None,
) -> pulumi.Output[BuiltImage]:
    """
    Builds a Docker image from a local directory and pushes it to Artifact Registry.

    - Builds the image using the given local_path as Docker context.
    - Pushes the image to Artifact Registry using a service account JSON key.
    - Returns image name and repo digest for later use.
    """
    # Artifact Registry image name format
    image_name = pulumi.Output.concat(
        f"{region}-docker.pkg.dev/",
        project,
        "/",
        repository.repository_id,
        "/",
        name,
    )

    # Read the service account key JSON
    if sa_key_path is None:
        # Matches: path.resolve(__dirname, "../credentials/service-account-key.json")
        # This file should sit one directory up from this module.
        module_dir = os.path.dirname(os.path.abspath(__file__))
        sa_key_path = os.path.normpath(os.path.join(module_dir, "..", "credentials", "service-account-key.json"))

    with open(sa_key_path, "r", encoding="utf-8") as f:
        sa_key_json = f.read()

    # Build and push image
    img = docker.Image(
        name,
        build=docker.DockerBuildArgs(
            context=local_path,
            platform="linux/amd64",  # Ensures compatibility with Cloud Run
        ),
        image_name=image_name,
        registry=docker.RegistryArgs(
            server=f"{region}-docker.pkg.dev",
            username="_json_key",
            password=sa_key_json,
        ),
        opts=pulumi.ResourceOptions(depends_on=[repository])
    )

    return pulumi.Output.from_input(
        {
            "image_name": img.image_name,
            "repo_digest": img.repo_digest,
        }
    )
