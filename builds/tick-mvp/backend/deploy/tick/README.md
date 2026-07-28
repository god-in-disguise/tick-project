# TICK private demo deployment

This deployment intentionally uses one DigitalOcean droplet in Frankfurt. It
runs only backend infrastructure: API, durable worker, market feed, venue event
monitor, Postgres, Redis, and Caddy.

The PWA is deployed independently to Vercel.

## Provision

```bash
cd terraform
export DIGITALOCEAN_TOKEN=...
terraform init
terraform apply \
  -var="ssh_key_fingerprint=..." \
  -var="droplet_name=tick-demo"
```

## Release backend

Create `.runtime/backend.env` from `backend.env.example`, then:

```bash
TICK_HOST=<droplet-ip> ./scripts/deploy_backend.sh
```

The public API hostname is `<droplet-ip>.sslip.io`. Caddy provisions TLS
automatically.
