# SafeSport production deployment

SafeSport: GitHub Actions builds the API image, the VPS runs PostgreSQL and Nginx, and a Cloudflare Origin Certificate secures the connection from Cloudflare to the VPS.

The VPS already uses ports `80/443` for Masqany and `8080/8443` for Jubilee. SafeSport therefore listens on TLS port `2053`. A Cloudflare Origin Rule maps the public hostname's normal HTTPS traffic to origin port `2053`, so clients still use `https://server.ayothealthsolutions.ke` without a port suffix.

## 1. Cloudflare DNS and TLS

### DNS record

Create this DNS record in the `ayothealthsolutions.ke` zone:

- Type: `A`
- Name: `server`
- IPv4 address: the public IPv4 address of `vmi3226662`
- Proxy status: **Proxied** (orange cloud)
- TTL: Auto

### Origin Certificate

In **SSL/TLS > Origin Server**, create an Origin Certificate covering `server.ayothealthsolutions.ke`. Store the two values on the VPS as:

```text
/home/deploy/apps/safesport/certs/cert.pem
/home/deploy/apps/safesport/certs/key.pem
```

The private key must never be committed to GitHub. Recommended permissions:

```bash
sudo install -d -o deploy -g deploy -m 700 /home/deploy/apps/safesport/certs
sudo chown deploy:deploy /home/deploy/apps/safesport/certs/cert.pem /home/deploy/apps/safesport/certs/key.pem
sudo chmod 644 /home/deploy/apps/safesport/certs/cert.pem
sudo chmod 600 /home/deploy/apps/safesport/certs/key.pem
```

Set the zone SSL/TLS encryption mode to **Full (strict)**.

### Origin Rule

Open **Rules > Origin Rules** and create a rule named `SafeSport origin port`:

- Expression: `(http.host eq "server.ayothealthsolutions.ke")`
- Destination Port: Rewrite to `2053`

This rule is required for the clean public URL because port `443` on the VPS belongs to Masqany. Without it, `https://server.ayothealthsolutions.ke` reaches the wrong container. Cloudflare supports destination-port overrides on all current plans.

Optionally enable **Always Use HTTPS** for the hostname or zone.

## 2. GitHub repository

Create a GitHub environment named `production` and add these environment secrets:

- `DOCKERHUB_TOKEN`
- `POSTGRES_PASSWORD` — generate a URL-safe value with `openssl rand -hex 32`
- `SECRET_KEY` — at least 32 random characters
- `ZOHO_SMTP_USERNAME`, `ZOHO_SMTP_PASSWORD`, `ZOHO_FROM_EMAIL`
- `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_MODEL_NAME`

Add these only when movement video storage uses a separate Cloudinary account:

- `MOVEMENT_CLOUDINARY_CLOUD_NAME`
- `MOVEMENT_CLOUDINARY_API_KEY`
- `MOVEMENT_CLOUDINARY_API_SECRET`

Create a GitHub variable named `SAFESPORT_FRONTEND_URL` with the exact HTTPS frontend origin and no trailing slash. For compatibility, the workflow also accepts `FRONTEND_URL`, and either name may be stored as a variable or secret. If it is environment-scoped, it must be defined inside the `production` environment.

No Cloudflare API token or tunnel token is required. The certificate and private key remain server-managed.

## 3. VPS runner and firewall

The existing Jubilee and Masqany runners are repository-scoped. Install a third GitHub Actions runner under `/home/deploy/actions-runner-safesport` using the command shown at **GitHub repository > Settings > Actions > Runners > New self-hosted runner**.

Configure it with:

- Runner name: `safesport-prod-runner`
- Additional label: `safesport-prod`
- Work folder: `_work`

From a root or sudo-capable shell, install and start it as the `deploy` user:

```bash
sudo /home/deploy/actions-runner-safesport/svc.sh install deploy
sudo /home/deploy/actions-runner-safesport/svc.sh start
```

Confirm that `deploy` can run Docker without sudo and that `/home/deploy/apps` is writable.

Allow inbound TCP port `2053` in the VPS/provider firewall. Prefer limiting the source to Cloudflare's published IPv4 and IPv6 ranges; otherwise allow the port temporarily and tighten it after verification. Do not change the existing `80`, `443`, `8080`, or `8443` mappings.

## 4. Automatic deployment

Every push to `main` automatically runs `.github/workflows/deploy.yml`. Manual `workflow_dispatch` remains available.

The workflow:

1. Runs the test suite.
2. Verifies that the server-managed certificate files exist.
3. Builds and pushes immutable and `latest` Docker image tags.
4. Writes protected production environment files under `/home/deploy/apps/safesport`.
5. Starts PostgreSQL, applies Alembic migrations, and starts the API and Nginx.
6. Verifies internal health and `https://server.ayothealthsolutions.ke/health`.

After the first successful deployment, create the initial system administrator:

```bash
cd /home/deploy/apps/safesport
docker exec -it safesport-api uv run --no-sync python -m scripts.seed_system_admin
```

## Operations

```bash
cd /home/deploy/apps/safesport
docker compose --env-file .env.compose -f docker-compose.prod.yml ps
docker compose --env-file .env.compose -f docker-compose.prod.yml logs -f safesport-api
docker compose --env-file .env.compose -f docker-compose.prod.yml logs -f safesport-nginx
```

Verify the origin directly from the VPS before enabling the Origin Rule:

```bash
curl --insecure --resolve server.ayothealthsolutions.ke:2053:127.0.0.1 \
  https://server.ayothealthsolutions.ke:2053/health
```

Back up `safesport-postgres` before destructive migrations. Named database and upload volumes are retained during normal deployments.
