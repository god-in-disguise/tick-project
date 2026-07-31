# TICK private demo deployment

This deployment intentionally uses one DigitalOcean droplet in Frankfurt. It
runs only backend infrastructure: API, durable worker, venue event listener,
Postgres, Redis, and Caddy.

The PWA is deployed independently to Vercel.

## Provision

```bash
cd terraform
export DIGITALOCEAN_TOKEN="$DO_API_TOKEN"
terraform init
terraform apply \
  -var="ssh_key_fingerprint=..." \
  -var="droplet_name=tick-demo"
```

## Release backend

Create `.runtime/backend.env` from `backend.env.example`, then:

```bash
TICK_HOST=<droplet-ip> \
TICK_SSH_KEY=.runtime/tick_ed25519 \
./scripts/deploy_backend.sh
```

The public API hostname is `api.tick.trading`. Its DNS `A` record points to the
droplet IP, and Caddy provisions TLS automatically.

## Runtime layout

```text
/opt/tick/backend   application source and image context
/opt/tick/deploy    Compose, Caddy, and private runtime environment
```

Postgres and Redis are private Docker-network services. Only SSH, HTTP, and
HTTPS are exposed by the droplet firewall.
