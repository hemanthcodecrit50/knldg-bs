pipeline {
    agent any

    environment {
        // AWS EC2 Target Server Settings
        // Modify these values in Jenkins Environment settings or directly here.
        EC2_USER          = 'ubuntu'
        EC2_HOST          = '54.172.226.216' // Replace with your EC2 IP/Domain
        EC2_PROJECT_PATH  = '/home/ubuntu/knldg-bs'
        
        // The ID of the SSH credentials configured in Jenkins (containing the .pem key)
        SSH_CREDENTIAL_ID = 'aws-ec2-ssh-key' 
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {
        stage('Checkout') {
            steps {
                echo 'Checking out source code...'
                checkout scm
            }
        }

        stage('Backend Unit Tests') {
            steps {
                echo 'Running Backend Unit Tests via pytest in isolated Python container...'
                // Running the tests in a clean docker container. 
                // Using pytest to test the SQLite chat store (doesn't require external database connections).
                sh '''
                    docker run --rm \
                      -v "${WORKSPACE}:/app" \
                      -w /app \
                      python:3.12-slim \
                      bash -c "pip install --no-cache-dir -r backend/requirements.txt pytest && pytest backend/app/tests/test_chat_store.py"
                '''
            }
        }

        stage('Frontend Build Verification') {
            steps {
                echo 'Verifying Frontend compilation and build...'
                // Running npm install and build in an isolated node container to verify typescript compilation and bundling.
                sh '''
                    docker run --rm \
                      -v "${WORKSPACE}/frontend:/app" \
                      -w /app \
                      node:20-alpine \
                      bash -c "npm ci && npm run build"
                '''
            }
        }

//         stage('Deploy to AWS EC2') {
//             steps {
//                 echo "Deploying application to AWS EC2 (${EC2_HOST})..."
//                 // Uses the SSH Agent plugin to authenticate using the private key configured in Jenkins credentials.
//                 sshagent(credentials: [env.SSH_CREDENTIAL_ID]) {
//                     sh '''
//                         ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} "
//                         set -e
//                         cd ${EC2_PROJECT_PATH} &&
//                         git fetch origin main &&
//                         git reset --hard origin/main &&
//                         docker-compose down &&
//                         docker-compose up --build -d
// "
//                     '''
//                 }
//             }
//         }
    }

    post {
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed. Please check the build console output for details.'
        }
    }
}
