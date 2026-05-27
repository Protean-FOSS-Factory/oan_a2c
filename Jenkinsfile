pipeline {
    agent any

    environment {
        AWS_REGION     = 'ap-south-1'
        AWS_ACCOUNT_ID = credentials('AWS_ACCOUNT_ID')
        GITHUB_TOKEN   = credentials('GITHUB_TOKEN')
        ECR_REPO       = 'oan-a2c'
        IMAGE_URI      = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"
        FRAPPE_BRANCH  = 'version-16'
        FRAPPE_PATH    = 'https://github.com/frappe/frappe'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Build Docker Image') {
            steps {
                sh '''
                    echo '[{"url":"https://github.com/Protean-FOSS-Factory/oan_a2c.git","branch":"develop"}]' > /tmp/apps.json
                    DOCKER_BUILDKIT=1 docker buildx build \
                        --build-arg FRAPPE_PATH=${FRAPPE_PATH} \
                        --build-arg FRAPPE_BRANCH=${FRAPPE_BRANCH} \
                        --secret id=apps_json,src=/tmp/apps.json \
                        --tag ${IMAGE_URI}:1.0.${BUILD_NUMBER} \
                        --tag ${IMAGE_URI}:latest \
                        --file images/layered/Containerfile \
                        --network=host \
                        --load \
                        --no-cache .
                '''
            }
        }

        stage('Push to ECR') {
            steps {
                sh '''
                    aws ecr get-login-password --region ${AWS_REGION} | \
                        docker login --username AWS --password-stdin \
                        ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
                    docker push ${IMAGE_URI}:1.0.${BUILD_NUMBER}
                    docker push ${IMAGE_URI}:latest
                '''
            }
        }

        stage('Trigger Deploy') {
            steps {
                sh '''
                    curl -X POST \
                      -H "Accept: application/vnd.github.v3+json" \
                      -H "Authorization: token ${GITHUB_TOKEN}" \
                      https://api.github.com/repos/Protean-FOSS-Factory/oan_a2c/dispatches \
                      -d '{"event_type": "jenkins-build-success"}'
                '''
            }
        }

        stage('Cleanup') {
            steps {
                sh '''
                    docker rmi ${IMAGE_URI}:1.0.${BUILD_NUMBER} || true
                    docker rmi ${IMAGE_URI}:latest || true
                    docker system prune -f || true
                '''
            }
        }
    }

    post {
        success { echo "Build and push successful!" }
        failure { echo "Build failed!" }
        sh "bash trigger-github.sh ${GITHUB_TOKEN} ${BUILD_NUMBER}"
    }
}