# Deployment Checklist

## 1. Prepare configs

```bash
mkdir -p configs
cp configs/api_keys.example.json configs/api_keys.json
touch titanos_live_state.json
python scripts/hash_api_key.py
```

Paste the hash into `configs/api_keys.json` and save the plaintext key somewhere safe.

## 2. Set environment

```bash
export TUNNEL_TOKEN="..."
export RESILEOS_CORS_ORIGINS="https://app.yourdomain.dev"   # optional
export RESILEOS_RATE_LIMIT_PER_MIN=60
```

The API key file is read from `configs/api_keys.json` (mounted read-only). You do not need `RESILEOS_API_KEYS` if the file is present.

## 3. Build and start

```bash
docker compose build
docker compose up -d
docker ps
```

Expected: the container appears with no `0.0.0.0:*` port mappings. Only the Cloudflare Tunnel connects outbound.

## 4. Verify auth

```bash
# Must be 401
curl -i http://127.0.0.1:8000/api/v1/stats

# Must be 200
curl -i http://127.0.0.1:8000/api/v1/stats \
  -H "X-API-Key: your-plaintext-key"
```

## 5. Verify the tunnel

```bash
curl -i https://api.yourdomain.dev/healthz
curl -i https://api.yourdomain.dev/api/v1/stats \
  -H "X-API-Key: your-plaintext-key"
```

## 6. Train and persist the substrate

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/train_substrate \
  -H "X-API-Key: your-plaintext-key" \
  -H "Content-Type: application/json" \
  -d '{"steps":10}'

docker compose restart

curl -s http://127.0.0.1:8000/api/v1/substrate_stats \
  -H "X-API-Key: your-plaintext-key"
```

`is_trained` and `training_steps` must survive the restart.

## 7. Rollback

```bash
docker compose down
docker compose up -d --force-recreate
```

State survives because it lives in named volumes, not the container.
