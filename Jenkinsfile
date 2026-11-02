pipeline {
    agent none

    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timestamps()
    }

    environment {
        REGISTRY_USER = 'ci-bot'
    }

    stages {
        stage('Build and Publish Staging Image') {
            agent { label 'built-in' }
            when {
                beforeAgent true
                branch 'develop'
            }
            options { timeout(time: 30, unit: 'MINUTES') }
            steps {
                checkout scm
                script {
                    env.REGISTRY_KAMPAN_IMAGE = "${env.REGISTRY_URL}/r202-coe-psu/kampan:develop-${env.BUILD_NUMBER}-${env.GIT_COMMIT.take(12)}"
                }
                withCredentials([
                    string(credentialsId: 'CI_REGISTRY_TOKEN', variable: 'REGISTRY_TOKEN')
                ]) {
                    sh '''
                        set -eu
                        : "${REGISTRY_URL:?Set the Jenkins REGISTRY_URL environment variable}"
                        DOCKER_CONFIG=$(mktemp -d)
                        export DOCKER_CONFIG
                        trap 'rm -rf "$DOCKER_CONFIG"' EXIT HUP INT TERM
                        printf '%s' "$REGISTRY_TOKEN" | docker login -u "$REGISTRY_USER" --password-stdin "$REGISTRY_URL"
                        docker build --pull -t "$REGISTRY_KAMPAN_IMAGE" .
                        docker push "$REGISTRY_KAMPAN_IMAGE"
                    '''
                }
            }
        }

        stage('Deploy to Staging') {
            agent { label 'staging-agent' }
            when {
                beforeAgent true
                branch 'develop'
            }
            options { timeout(time: 10, unit: 'MINUTES') }
            steps {
                checkout scm
                withCredentials([
                    string(credentialsId: 'CI_REGISTRY_TOKEN', variable: 'REGISTRY_TOKEN'),
                    file(credentialsId: 'INVENTORY_ENV_DEVELOPMENT', variable: 'CFG_FILE')
                ]) {
                    sh 'sh scripts/deploy-staging.sh'
                }
            }
        }

        stage('Deploy to Production') {
            agent { label 'mgmt' }
            when {
                beforeAgent true
                branch 'main'
            }
            steps {
                withCredentials([
                    sshUserPrivateKey(credentialsId: 'kampan-prod-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
                    string(credentialsId: 'kampan-prod-host', variable: 'SSH_HOST'),
                    string(credentialsId: 'kampan-prod-port', variable: 'SSH_PORT')
                ]) {
                    sh '''
                        echo "Starting deployment to Production server..."
                        
                        ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST "
                            echo '==> Deploying kampan...'
                            cd /home/projects/kampan
                            sudo git -C /home/projects/kampan fetch origin main
                            sudo git -C /home/projects/kampan checkout main
                            sudo git -C /home/projects/kampan reset --hard origin/main
                            sudo git -C /home/projects/kampan pull origin main
                            sudo docker compose -f docker-compose.yml up -d --build --force-recreate
                        "
                        echo "Deployment process finished successfully!"
                    '''
                }
            }
        }
    }
}
