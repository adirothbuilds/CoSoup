# Archive and database recovery

Before enabling local eviction, keep an offline copy of the private 32-byte archive key and test recovery on an empty PostgreSQL 17 instance. Never tar a running PostgreSQL data directory as a logical backup. Keep old keys when rotating; archives identify their key by a public fingerprint, and a lost key cannot be reconstructed from an object.

## Catalog available

Read authorized artifacts from `/api/v1/storage/artifacts`. Submit their IDs to `/api/v1/storage/restore-jobs`, inspect job errors, and resume the blocked analysis only after the restore succeeds. Each restore reserves bounded local space and validates encrypted-object and member hashes. Restored originals retain their catalog identity and a configurable eviction-protection TTL.

## Catalog lost

1. Stop the API and workers; preserve surviving data and credentials. Do not overwrite the failed database in place.
2. List the private R2 prefix through the operator's authorized R2 interface. Download the required encrypted backup/data shards, preserving object keys, timestamps and any independent encrypted-object checksum. The S3 ETag is not a SHA-256 verification. Remote listing/download through this operator workflow is separate from the API's catalog-driven restore.
3. Authenticate and unpack each downloaded object without needing a database. The following container command reads the private downloaded file/key and publishes opaque artifact-ID filenames into a **new** directory:

```sh
docker run --rm --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/srv/stock-scanner,dst=/private \
  stock-scanner-server:local recover-archive \
  --file /private/recovery/download.tar.zst.aesgcm \
  --key-file /private/secrets/archive_key \
  --destination /private/recovery/unpacked \
  --max-bytes 1000000000
```

Supply `--expected-sha256` when an independently recorded encrypted-object hash survives. The authenticated encryption tag and internal manifest/member checks are always required. Recovery rejects duplicate/unsafe members, oversized expansion and existing destinations; manifest paths are metadata, never extraction destinations. Ensure sufficient quota for the encrypted copy, decrypted compressed staging and expanded members.

4. Read `unpacked/manifest.json` privately to identify the member whose dataset is `backup`. The corresponding opaque filename is a PostgreSQL custom-format dump. Inspect it with PostgreSQL 17 `pg_restore --list`; restore into a fresh disposable instance before production. Use credentials through a private `.pgpass` or secret-file wrapper, never a password argument. Restore with `--no-owner --no-privileges` using the fresh administrator, then run the explicit migration/role bootstrap to recreate the service grants from separately provisioned role passwords.
5. The dump restores the catalog as of its backup time. Recover older market/report/upload shards according to their manifests and verify hashes before placing their bytes in managed storage. For catalog entries covered by the dump, prefer the API restore path. Objects/new records created after the selected dump can require manual catalog reconciliation; do not claim automatic recovery of every later job or journal entry.
6. Run readiness checks, compare portfolio/journal counts and artifact hashes, test an authorized report/scan, then resume scheduling. Keep the previous instance until the drill is verified.

Nightly dumps do not include future journal changes, fresh upload bytes, deployment secrets or the archive key. Monthly batches have a different data-loss window. More frequent backups and daily unique-upload batches are configurable; point-in-time WAL recovery and a remote catalog-discovery/reconciliation adapter are future extensions.
