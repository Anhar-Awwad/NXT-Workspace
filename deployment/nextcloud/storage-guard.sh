#!/bin/sh
set -eu
# Prevents Nextcloud from starting if storage type (local disk vs Azure Blob)
# changed without migrating existing files — avoids files silently vanishing.
php -r '
$config = [];
$file = "/var/www/html/config/config.php";
if (is_file($file)) {
    $CONFIG = [];
    require $file;
    $config = $CONFIG;
}
$saved_uses_objectstore = !empty($config["objectstore"]) || !empty($config["objectstore_multibucket"]);
$env_wants_objectstore = getenv("OBJECTSTORE_AZURE_ACCOUNT") && getenv("OBJECTSTORE_AZURE_KEY") && getenv("OBJECTSTORE_AZURE_CONTAINER");

if (empty($config)) {
    exit(0);
}

if ($saved_uses_objectstore && !$env_wants_objectstore) {
    fwrite(STDERR, "This instance was set up with Azure Blob object storage, but OBJECTSTORE_AZURE_* is no longer set. Stop and follow docs/storage-migration.md before switching to local files.\n");
    exit(1);
}
if (!$saved_uses_objectstore && $env_wants_objectstore) {
    fwrite(STDERR, "This instance was set up with local disk storage, but OBJECTSTORE_AZURE_* is now set. Stop and follow docs/storage-migration.md before switching to Azure Blob.\n");
    exit(1);
}
if (isset($config["datadirectory"]) && $config["datadirectory"] !== "/var/www/html/data") {
    fwrite(STDERR, "Unexpected data directory; this deployment backs up /var/www/html/data only.\n");
    exit(1);
}
'