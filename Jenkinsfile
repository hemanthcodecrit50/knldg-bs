pipeline {
  agent any

  environment {
    DOCKER_HOST = "unix:///var/run/docker.sock"
  }

  stages {
    stage('Checkout') {
      steps {
        dir('/workspace') {
          checkout scm
        }
      }
    }

    stage('Build') {
      steps {
        sh 'docker build -t queryfile-backend -f /workspace/backend/Dockerfile /workspace/backend || true'
        sh 'docker build -t queryfile-frontend -f /workspace/frontend/Dockerfile /workspace/frontend || true'
      }
    }

    stage('Test') {
      steps {
        sh 'BACKEND_URL=http://backend:8000 bash /workspace/scripts/smoke_test.sh'
      }
    }

    stage('Sync') {
      steps {
        sh 'python3 backend/app/sync/sync.py'
      }
    }

    stage('Deploy') {
      steps {
        sh 'docker compose -f /workspace/docker-compose.yml up -d --build'
      }
    }
  }

  post {
    always {
      sh 'docker ps || true'
      sh 'docker logs --tail 200 queryfile-backend || true'
    }
  }
}
