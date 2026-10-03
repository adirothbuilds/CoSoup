import shutil

from sqlalchemy import select

from ...adapters.extraction import LocalExtractor
from ...errors import ServiceError
from ...persistence.models import Artifact, Import
from ...services.jobs import owned


def handle(context, extractor=None):
    owner, storage = context.job.owner_id, context.storage
    with context.database.session() as db:
        row = owned(db, Import, context.job.payload["import_id"], owner)
        if row.status in {"confirmed", "rejected"}:
            return {"import_id": row.id, "status": row.status}
        artifact = owned(db, Artifact, row.upload_id, owner)
        storage.reserve(db, context.job.id, owner, context.settings.limits.import_reservation_bytes)
        original = storage.read(artifact)
        media_type = artifact.metadata_["media_type"]
        duplicates = list(db.scalars(select(Artifact.id).where(Artifact.owner_id == owner, Artifact.dataset == "uploads",
                                   Artifact.sha256 == artifact.sha256, Artifact.id != artifact.id)))
    workspace = storage.path(f"job-workspaces/{context.job.id}-{context.job.lease_token}")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = workspace/("source"+original.suffix)
    shutil.copyfile(original, source)
    source.chmod(0o600)
    try:
        extractor = extractor or LocalExtractor(context.settings)
        proposal = extractor.extract(source, media_type, workspace, context.checkpoint)
        proposal["duplicate_upload_ids"] = duplicates
        proposal["document_sha256"] = artifact.sha256
        with context.database.session() as db:
            row = owned(db, Import, context.job.payload["import_id"], owner, lock=True)
            if row.status != "rejected":
                row.proposal, row.status = proposal, "awaiting_review"
        return {"import_id": row.id, "status": row.status}
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
