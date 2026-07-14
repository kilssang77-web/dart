#!/bin/bash
# Deploy prism.py dynamic scan range fix
# Run after Docker Desktop is restarted

CONTAINER=bid_backend

docker cp bid-system/backend/app/ml/prism.py $CONTAINER:/app/app/ml/prism.py
docker cp bid-system/backend/app/services.py $CONTAINER:/app/app/services.py
docker cp bid-system/backend/app/api/v1/recommend.py $CONTAINER:/app/app/api/v1/recommend.py

# Restart the backend to pick up changes
docker restart $CONTAINER

echo "Done. Check: docker logs $CONTAINER --tail 20"
