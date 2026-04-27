pipeline {
  agent any

  options {
    skipDefaultCheckout(true)
  }

  environment {
    DOCKER_HOST = "unix:///var/run/docker.sock"
  }

  stages {
    stage('Up') {
      steps {
        sh 'docker compose -f /workspace/docker-compose.yml up -d --build'
      }
    }

    stage('Test') {
      steps {
        sh 'for i in $(seq 1 20); do curl -sf http://backend:8000/health && break; sleep 3; done'
        sh 'BACKEND_URL=http://backend:8000 bash /workspace/scripts/smoke_test.sh'
      }
    }

    stage('Sync') {
      steps {
        sh 'docker compose -f /workspace/docker-compose.yml exec -T backend python -m backend.app.sync.sync'
      }
    }

    stage('Deploy') {
      steps {
        sh 'docker compose -f /workspace/docker-compose.yml up -d --build --wait'
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
