# delete only the contents of `./backend/api_gateway/alembic/versions`
#!/bin/bash
set -e
# Remove all files in the versions directory
rm -rf ./backend/api_gateway/alembic/versions/*

docker-compose down -v
docker-compose up -d --build
docker-compose run --rm api_gateway bash -c "alembic revision --autogenerate -m 'Initial schema with chat groups' && alembic upgrade head"