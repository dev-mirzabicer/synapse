# delete only the contents of `./backend/api_gateway/alembic/versions`
#!/bin/bash
set -e
# Remove all files in the versions directory
rm -rf ./backend/api_gateway/alembic/versions/*

docker-compose down -v
docker compose build --no-cache orchestrator_service
docker-compose up -d
# Wait for the database to be ready
sleep 10
docker-compose run --rm api_gateway bash -c "alembic revision --autogenerate -m 'Initial schema with chat groups' && alembic upgrade head"