# Deployment Information

## Public URL
https://day14-ai-agent.onrender.com

## Platform
Render (Web Service, Root Directory: `03-cloud-deployment/railway`, Region: Singapore, Plan: Free)

## Test Commands

### Health Check
```bash
curl https://day14-ai-agent.onrender.com/health
# Expected: {"status": "ok", ...}
```

### API Test
```bash
curl -X POST https://day14-ai-agent.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello from Render"}'
# Expected: 200 OK with "answer"
```

### PowerShell Test (Windows)
```powershell
$url = "https://day14-ai-agent.onrender.com"
Invoke-RestMethod "$url/health"
$body = @{ question = "Hello from Render" } | ConvertTo-Json
Invoke-RestMethod "$url/ask" -Method Post -ContentType "application/json" -Body $body
```

## Environment Variables Set
- `PYTHON_VERSION=3.11.0`
- `ENVIRONMENT=production`
- `AGENT_API_KEY` (configured as secret on Render Dashboard)

> Ghi chú: Đối với bản tổng hợp cuối ở `06-lab-complete/` (có `X-API-Key`, rate limit và cost guard qua Redis), `06-lab-complete/render.yaml` và `06-lab-complete/railway.toml` đã được cấu hình sẵn để deploy container Docker hoàn chỉnh.

## Screenshots
- [Render Swagger Docs (Running)](screenshots/running.png)
- [Render Health Check Test](screenshots/test.png)
