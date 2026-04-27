FROM node:18
WORKDIR /app
COPY frontend/package*.json /app/
RUN npm install
COPY frontend /app
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
