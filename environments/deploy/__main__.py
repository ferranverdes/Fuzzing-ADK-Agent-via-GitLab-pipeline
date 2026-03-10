import os
import sys
from pathlib import Path

import pulumi
import pulumi_gcp as gcp

# Add the environments root directory to sys.path so Python can find sibling packages (e.g. ../modules)
sys.path.append(str(Path(__file__).resolve().parent.parent))

from modules.artifact_registry import BuiltImage
from modules.cloud_run import (
    deploy_public_cloud_run
)

# ------------------------------------------------------------
# 1. Load Pulumi and GCP configuration values
# ------------------------------------------------------------

config = pulumi.Config()
env = config.require("env")

gcp_config = pulumi.Config("gcp")
project = gcp_config.require("project")
region = gcp_config.require("region")
zone = gcp_config.get("zone") or "europe-west1-b"

# ------------------------------------------------------------
# 2. Read image details from environment variables (required)
# ------------------------------------------------------------

ollama_image_name = os.getenv("OLLAMA_IMAGE_NAME")
ollama_image_digest = os.getenv("OLLAMA_IMAGE_DIGEST")
agent_image_name = os.getenv("AGENT_IMAGE_NAME")
agent_image_digest = os.getenv("AGENT_IMAGE_DIGEST")

if not ollama_image_name or not ollama_image_digest:
    raise ValueError(
        "Missing required environment variables: OLLAMA_IMAGE_NAME and/or OLLAMA_IMAGE_DIGEST. "
        "Ensure they are exported from the build stage or provided in CI/CD."
    )

if not agent_image_name or not agent_image_digest:
    raise ValueError(
        "Missing required environment variables: AGENT_IMAGE_NAME and/or AGENT_IMAGE_DIGEST. "
        "Ensure they are exported from the build stage or provided in CI/CD."
    )

# Prepare image object expected by Cloud Run deploy function.
ollama_image: BuiltImage = {
    "image_name": ollama_image_name,
    "repo_digest": ollama_image_digest,
}

agent_image: BuiltImage = {
    "image_name": agent_image_name,
    "repo_digest": agent_image_digest,
}


# ------------------------------------------------------------
# 3. Set a GCP provider using service account credentials
# ------------------------------------------------------------

current_dir = os.path.dirname(os.path.abspath(__file__))
sa_key_path = os.path.join(current_dir, "..", "credentials", "service-account-key.json")

with open(sa_key_path, "r", encoding="utf-8") as f:
    credentials_json = f.read()

provider = gcp.Provider(
    "gcp-provider",
    credentials=credentials_json,
    project=project,
    region=region,
    zone=zone,
)


# ------------------------------------------------------------
# 4. Deploy a public Cloud Run service
# ------------------------------------------------------------

ollama_backend_url = deploy_public_cloud_run(
    "ollama-backend",
    ollama_image,
    env,
    region,
    provider,
    env_vars={
        "OLLAMA_NUM_PARALLEL": 4
    },
    max_instances=3,
    cpu="8",
    memory="16Gi",
    gpu=1,
    gpu_type="nvidia-l4",
)

# ------------------------------------------------------------
# 5. Deploy a public Cloud Run service for the ADK Agent
# ------------------------------------------------------------

agent_url = deploy_public_cloud_run(
    "adk-agent",
    agent_image,
    env,
    region,
    provider,
    env_vars={
        "OLLAMA_API_BASE": ollama_backend_url
    }
)

# ------------------------------------------------------------
# 6. Export stack outputs
# ------------------------------------------------------------

pulumi.export("env", env)
pulumi.export("project", project)
pulumi.export("region", region)
pulumi.export("zone", zone)
pulumi.export("ollama_backend_url", ollama_backend_url)
pulumi.export("agent_url", agent_url)
