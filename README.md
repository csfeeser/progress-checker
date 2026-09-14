# Student Status Board

A dead-simple classroom status board. Students mark themselves 🔵 **Working**, 🟢 **Good to Go**, or 👻 **Away**; the instructor watches everyone's status live from `/admin`.

All state lives in server memory only — nothing is persisted, and restarting the container clears the roster.

## Run it

```
docker run -d --name status-board -p 2225:2225 --restart unless-stopped ghcr.io/csfeeser/progress-checker:latest
```

This runs the container in the background, listening on `0.0.0.0:2225` (reachable from other machines on the network). Then open:

- `http://<server-ip>:2225` — student view
- `http://<server-ip>:2225/admin` — admin dashboard (password: `alta3`)

Or with Docker Compose:

```
docker compose up -d
```

## Build locally

```
docker build -t progress-checker .
docker run -d -p 2225:2225 progress-checker
```

Pushing to `main` triggers `.github/workflows/docker-publish.yml`, which builds and publishes the image to GHCR automatically.
