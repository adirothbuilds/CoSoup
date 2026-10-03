import json
import io
import shutil
from pathlib import Path

from ...adapters.codex import CodexCLI
from ...errors import ServiceError
from ...persistence.models import Artifact
from ...services.jobs import owned
from ...services.reports import publish, published


def handle(context, analyst=None):
    existing = published(context, "agent")
    if existing:
        return existing
    request, storage, owner = context.job.payload, context.storage, context.job.owner_id
    if request.get("profile_id", "research-analyst") != "research-analyst":
        raise ServiceError("invalid_profile", "Unknown trusted analyst profile")
    if request.get("portfolio_id") and not request.get("allow_portfolio_data"):
        raise ServiceError("portfolio_export_denied", "Portfolio export was not explicitly authorized", 403)
    if request.get("allow_current_web_research"):
        raise ServiceError("web_research_disabled", "This analyst profile is limited to approved local inputs")
    workspace = storage.path(f"job-workspaces/{context.job.id}-{context.job.lease_token}")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with context.database.session() as db:
            storage.reserve(db, context.job.id, owner, context.settings.limits.agent_reservation_bytes)
            from ...services.agent_context import context_packet
            from PIL import Image
            inputs = context_packet(db, storage, context.settings, owner, request)
            end = inputs["end_date"]
            if not inputs["reports"] and request["task_type"] not in {"portfolio_review", "document_review"}:
                raise ServiceError("missing_reports", "No authorized reports exist for the requested period; scan or restore first")
            image_bytes = 0
            for i, image in enumerate(inputs["images"]):
                artifact = owned(db, Artifact, image["id"], owner)
                with storage.reader():
                    source = storage.read(artifact, context.settings.limits.upload_bytes)
                    try:
                        with Image.open(source) as original:
                            if original.width*original.height > context.settings.limits.image_pixels:
                                raise ServiceError("image_pixel_limit", "Image exceeds the configured pixel budget", 413)
                            original.load()
                            destination = workspace/f"vision-{i}.png"
                            encoded = io.BytesIO()
                            original.convert("RGB").save(encoded, format="PNG")
                            image_bytes += encoded.tell()
                            if image_bytes > context.settings.limits.agent_reservation_bytes//2:
                                raise ServiceError("agent_image_budget", "Decoded images exceed the configured agent workspace budget", 413)
                            destination.write_bytes(encoded.getvalue())
                            destination.chmod(0o600)
                    except (OSError, ValueError, Image.DecompressionBombError):
                        raise ServiceError("invalid_vision_image", "Image could not be safely decoded", 422) from None
                image["workspace_file"] = destination.name
        body = json.dumps(inputs)
        if len(body.encode()) > context.settings.limits.agent_reservation_bytes//2:
            raise ServiceError("agent_input_limit", "Approved inputs exceed the configured agent workspace budget")
        (workspace/"inputs.json").write_text(body)
        trusted = Path(__file__).resolve().parents[2]/"profiles/research-analyst.md"
        (workspace/"AGENTS.md").write_text(trusted.read_text())
        result = (analyst or CodexCLI(context.settings)).analyze(workspace, request, context.checkpoint)
        allowed = set(inputs["source_ids"])
        if set(result["sources"])-allowed:
            raise ServiceError("agent_unapproved_source", "Agent result cites sources outside its authorized inputs")
        result.update(status="complete" if not result["gaps"] else "partial_coverage", data_date=end,
                      provenance={"job_id": context.job.id, "source_ids": inputs["source_ids"], "profile_id": "research-analyst",
                                  "portfolio_export_authorized": bool(request.get("allow_portfolio_data")),
                                  "document_export_authorized": bool(request.get("allow_uploaded_documents"))})
        return publish(context, end, "agent", result, result["markdown"])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
