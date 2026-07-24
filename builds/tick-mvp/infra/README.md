# Infra

Deployment target:

- DigitalOcean for backend processes.
- Vercel for frontend PWA.
- Docker Compose first for backend processes only.
- Terraform can be added here once the service shape is stable.

Keep secrets out of git. Backend runtime env lives in `../backend/.env.example`; frontend env should be owned by the frontend/Vercel project.
