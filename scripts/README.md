# Scripts

## Verify a deployed Iskra service

After setting `API_TOKEN` in the current Termux shell, run:

```bash
chmod +x scripts/verify-deployment.sh
API_TOKEN='your-secret' scripts/verify-deployment.sh https://your-service.onrender.com
```

The script checks the health endpoint, public workspace shell, anonymous API rejection, and administrator authentication. It does not create a tenant or upload documents.
