pipeline {
  agent any

  environment {
    DOCKER_HOST = "unix:///var/run/docker.sock"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Build') {
      steps {
        sh 'docker build -t queryfile-backend -f backend/Dockerfile backend || true'
        sh 'docker build -t queryfile-frontend -f frontend/Dockerfile frontend || true'
      }
    }

    stage('Test') {
      steps {
        sh './scripts/smoke_test.sh'
      }
    }

    stage('Sync') {
      steps {
        sh 'python3 backend/app/sync/sync.py'
      }
    }

    stage('Deploy') {
      steps {
        sh 'docker-compose up -d --build'
      }
    }
  }

  post {
    always {
      sh 'docker ps || true'
    }
  }
}
