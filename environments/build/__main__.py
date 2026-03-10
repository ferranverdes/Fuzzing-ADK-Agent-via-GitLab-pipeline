import sys
import os
import pulumi
import pulumi_gcp as gcp
from pathlib import Path

# Add the environments root directory to sys.path so Python can find sibling packages (e.g. ../modules)
sys.path.append(str(Path(__file__).resolve().parent.parent))

from modules.artifact_registry import (
    build_and_push_docker_image,
    create_artifact_registry_repository,
)
from modules.compute_engine import enable_compute_engine_api
from modules.resource_manager import enable_resource_manager_api


# ------------------------------------------------------------
# 1. Load Pulumi configuration
# ------------------------------------------------------------

config = pulumi.Config()
env = config.require("env")

gcp_config = pulumi.Config("gcp")
project = gcp_config.require("project")
region = gcp_config.require("region")
zone = gcp_config.get("zone") or "europe-west1-b"


# ------------------------------------------------------------
# 2. Set a GCP provider using service account credentials
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
# 3. Enable required APIs
# ------------------------------------------------------------

compute_engine_api = enable_compute_engine_api(project, provider)
resource_manager_api = enable_resource_manager_api(project, provider)


# ------------------------------------------------------------
# 4. Create Artifact Registry repository
# ------------------------------------------------------------

repository = create_artifact_registry_repository(
    "adk-agent-repo",
    region,
    provider,
    depends_on=[
        compute_engine_api,
        resource_manager_api,
    ],
)


# ------------------------------------------------------------
# 5. Build and push Docker image - Ollama backend
# ------------------------------------------------------------

app_path = os.path.normpath(os.path.join(current_dir, "..", "..", "ollama-backend"))

ollamaImage = build_and_push_docker_image(
    name="ollama-backend",
    local_path=app_path,
    project=project,
    region=region,
    repository=repository,
)


# ------------------------------------------------------------
# 6. Build and push Docker image - ADK Agent
# ------------------------------------------------------------

app_path = os.path.normpath(os.path.join(current_dir, "..", "..", "adk-agent"))

agentImage = build_and_push_docker_image(
    name="adk-agent",
    local_path=app_path,
    project=project,
    region=region,
    repository=repository,
)


# ------------------------------------------------------------
# 7. Export stack outputs
# ------------------------------------------------------------

pulumi.export("env", env)
pulumi.export("project", project)
pulumi.export("region", region)
pulumi.export("zone", zone)
pulumi.export("ollama_image_name", ollamaImage["image_name"])
pulumi.export("ollama_repo_digest", ollamaImage["repo_digest"])
pulumi.export("agent_image_name", agentImage["image_name"])
pulumi.export("agent_repo_digest", agentImage["repo_digest"])
