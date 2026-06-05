pipeline {
    agent any

    environment {
        // Git Configuration
        GIT_REPO_URL      = 'https://github.com/hemanthcodecrit50/knldg-bs.git'
        GIT_BRANCH        = 'aws-ec2' // Your active branch
        // If your repository is private, create credentials in Jenkins and set the ID here:
        // GIT_CREDENTIAL_ID = 'github-credentials-id'

        // AWS EC2 Target Server Settings
        EC2_USER          = 'ubuntu'
        EC2_HOST          = '54.172.226.216'
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
                echo "Checking out source code from ${GIT_REPO_URL} (branch: ${GIT_BRANCH})..."
                git branch: env.GIT_BRANCH, 
                    url: env.GIT_REPO_URL
            }
        }

        stage('Backend Unit Tests') {
            steps {
                echo 'Running Backend Unit Tests via pytest in isolated Python container...'
                sh '''
                    docker run -d --name test-backend python:3.12-slim sleep 3600
                    
                    trap "docker rm -f test-backend" EXIT
                    
                    echo 'Copying files into container...'
                    docker cp . test-backend:/app
                    
                    echo 'Running tests...'
                    docker exec -w /app test-backend bash -c "pip install --no-cache-dir -r backend/requirements.txt pytest && pytest backend/app/tests/test_chat_store.py"
                '''
            }
        }

        stage('Frontend Build Verification') {
            steps {
                echo 'Verifying Frontend compilation and build...'
                sh '''
                    docker run -d --name test-frontend node:20-alpine sleep 3600
                    
                    trap "docker rm -f test-frontend" EXIT
                    
                    echo 'Copying files into container...'
                    docker cp frontend/. test-frontend:/app
                    
                    echo 'Building frontend...'
                    docker exec -w /app test-frontend sh -c "npm ci && npm run build"
                '''
            }
        }

        stage('Deploy to AWS EC2') {
            steps {
                echo "Deploying application to AWS EC2 (${EC2_HOST})..."
                sshagent(credentials: [env.SSH_CREDENTIAL_ID]) {
                    sh '''
                        ssh -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} "
                            set -e
                            cd ${EC2_PROJECT_PATH}
                            
                            echo 'Fetching latest changes from Git...'
                            git fetch origin ${GIT_BRANCH}
                            git reset --hard origin/${GIT_BRANCH}
                            
                            echo 'Rebuilding and restarting docker containers...'
                            if command -v docker-compose &> /dev/null; then
                                docker-compose down
                                docker-compose up --build -d
                            else
                                docker compose down
                                docker compose up --build -d
                            fi
                        "
                    '''
                }
            }
        }
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
