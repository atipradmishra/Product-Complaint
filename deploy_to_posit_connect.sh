echo "Generating manifest..."
rsconnect write-manifest flask \
    --overwrite \
    --entrypoint app.py \
    "."

rsconnect deploy manifest \
    --server "https://connect.apollo.roche.com/" \
    --api-key "" \
    --app-id 11851 \
    --title "oceanside-backend" \
    --insecure \
    --verbose \
    "manifest.json"