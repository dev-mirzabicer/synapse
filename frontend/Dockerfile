# frontend/Dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Expose port 3000
EXPOSE 3000

# Start the app
CMD ["npm", "run", "dev"]