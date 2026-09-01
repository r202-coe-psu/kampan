pipeline {
    agent none
    
    environment {
        CFG_FILE_ID = "${BRANCH_NAME == 'main' ? 'INVENTORY_CFG_PRODUCTION' : 'INVENTORY_CFG_DEVELOPMENT'}"
        ENVIRONMENT = "${BRANCH_NAME == 'main' ? 'production' : 'development'}"
        REGISTRY_INVENTORY_IMAGE = "${REGISTRY_URL}/r202-coe-psu/kampan"
        VERSION = "1.0.0"
        REGISTRY_USER = "bomzyx"
    }
    
    stages {
        stage('Checkout') {
            agent { label 'built-in' }
            when {
                branch 'develop'
            }
            steps {
                checkout scm
            }
        }
        stage('Lint Dockerfile') {
            agent { 
                docker {
                    image 'hadolint/hadolint:latest-debian'
                    args '-v $PWD:/workdir'
                }
            }
            when {
                branch 'develop'
            }
            steps {
                script {
                    sh 'hadolint --failure-threshold error Dockerfile > hadolint_report.txt'
                    archiveArtifacts artifacts: 'hadolint_report.txt'
                }
            }
        }
        stage('Build docker image') {
            agent { label 'built-in' }
            when {
                branch 'develop'
            }
            steps {
                script {
                    sh """
                        docker build -t \"$REGISTRY_INVENTORY_IMAGE:${VERSION}\" .
                        docker tag \"$REGISTRY_INVENTORY_IMAGE:${VERSION}\" \"$REGISTRY_INVENTORY_IMAGE:latest\"
                    """
                }
            }
        }
        stage('Code Analysis Pylint/Pyre') {
            agent { label 'built-in' }
            when {
                branch 'develop'
            }
            steps {
                script {
                    docker.image('python:3.12').inside('-v $PWD:/app') {
                        // Install Poetry and tools
                        sh 'pip install poetry pyre-check pylint'

                        // Install project dependencies 
                        sh 'poetry config virtualenvs.create false'
                        sh 'poetry install --no-interaction'

                        // Run analysis
                        sh '''
                        SITE_PACKAGES=$(python -c "import site; print(site.getsitepackages()[0])")
                        echo '{
                            "source_directories": [
                                "."
                            ],
                            "search_path": [
                                "'$SITE_PACKAGES'"
                            ]
                        }' > .pyre_configuration
                        '''
                        sh 'cat .pyre_configuration'
                        def pylintStatus = sh(script: 'poetry run pylint INVENTORY > pylint_report.txt || true', returnStatus: true)
                        def pyreStatus = sh(script: 'poetry run pyre check > pyre_report.txt || true', returnStatus: true)
                        archiveArtifacts artifacts: 'pylint_report.txt, pyre_report.txt'

                        if (pylintStatus > 8) {
                            error "Critical Pylint issues detected, stopping pipeline!"
                        }
                        if (pyreStatus != 0) {
                            error "Critical Pyre type check issues detected, stopping pipeline!"
                        }
                    }
                }
            }
        }
        // stage('SonarQube Analysis') {
        //     agent { 
        //         label 'built-in'
        //     }
        //     when {
        //         branch 'develop'
        //     }
        //     steps {
        //         script {
        //             def scannerHome = tool 'SonarScanner'
        //             withCredentials([string(credentialsId: 'SONARQUBE_TOKEN', variable: 'SONAR_TOKEN')]) {
        //                 withSonarQubeEnv() {
        //                     sh "${scannerHome}/bin/sonar-scanner -Dsonar.login=${SONAR_TOKEN}"
        //                 }
        //             }
        //         }
        //     }
        // }
        stage('Upload docker image to registry') {
            agent { 
                label 'built-in'
            }
            when {
                branch 'develop'
            }
            steps {
                withCredentials([string(credentialsId: 'DOCKER_REGISTRY_TOKEN', variable: 'REGISTRY_TOKEN')]) {
                    sh 'echo "$REGISTRY_TOKEN" | docker login -u "$REGISTRY_USER" --password-stdin "$REGISTRY_URL"'
                    sh """
                        docker push \"$REGISTRY_INVENTORY_IMAGE:latest\"
                        docker push \"$REGISTRY_INVENTORY_IMAGE:${VERSION}\"
                    """
                }
            }
        }
        stage('Deploy to Staging') {
            agent { label 'staging-agent' }
            when {
                branch 'develop'
            }
            steps {
                // checkout scm

                withCredentials([
                    string(credentialsId: 'DOCKER_REGISTRY_TOKEN', variable: 'REGISTRY_TOKEN'),
                    file(credentialsId: "${CFG_FILE_ID}", variable: 'CFG_FILE')
                ]) {
                    // Login to Docker Registry
                    sh 'echo "$REGISTRY_TOKEN" | docker login -u "$REGISTRY_USER" --password-stdin "$REGISTRY_URL"'
                    
                    // Pull the latest Docker image
                    sh "docker pull \"$REGISTRY_INVENTORY_IMAGE:latest\""
                    
                    // Copy config file to deployment directory
                    sh "cp \$CFG_FILE kampan-${ENVIRONMENT}.cfg"

                    echo 'Deploying to Staging'
                    
                    // Use docker compose for deployment with config file mounted via volume
                    sh """
                        ENVIRONMENT=${ENVIRONMENT} \
                        REGISTRY_URL=${REGISTRY_URL} \
                        REGISTRY_INVENTORY_IMAGE=${REGISTRY_INVENTORY_IMAGE} \
                        KAMPAN_CFG_FILE=\$(pwd)/kampan-${ENVIRONMENT}.cfg \
                        docker compose -f docker-compose.develop.yml down --remove-orphans
                        docker compose -f docker-compose.develop.yml pull
                        KAMPAN_CFG_FILE=\$(pwd)/kampan-${ENVIRONMENT}.cfg \
                        docker compose -f docker-compose.develop.yml up -d
                        docker volume prune -f
                    """
                    
                    // Verify the containers are running
                    sh '''
                        echo "Verifying containers..."
                        docker ps --format "table {{.Names}}\t{{.Status}}" | grep "INVENTORY-.*-development"
                    '''
                    
                    // Clean up unused images
                    sh 'docker image prune -f'
                }
            }
            post {
                always {
                    sh "rm -f kampan-${ENVIRONMENT}.cfg"
                    sh 'docker logout "$REGISTRY_URL"'
                }
                success {
                    echo 'Deployment to Staging completed successfully'
                    sh '''
                        echo "Running containers:"
                        docker ps --format "table {{.Names}}\t{{.Status}}" | grep "INVENTORY-.*-development"
                    '''
                }
                failure {
                    echo 'Deployment to Staging failed'
                    sh '''
                        echo "Container logs:"
                        for container in $(docker ps -a --format "{{.Names}}" | grep "INVENTORY-.*-development"); do
                            echo "=== $container logs ==="
                            docker logs $container
                        done
                    '''
                }
            }
        }
        stage('Deploy to Production') {
            agent { label 'staging-agent' }
            when {
                branch 'main'
            }
            steps {
                echo 'Deploying to Production'
                // withCredentials([
                //     usernamePassword(credentialsId: 'DOCKER_REGISTRY_LOGIN', usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD'),
                //     file(credentialsId: "${ENV_FILE_ID}", variable: 'ENV_FILE')
                // ]) {
                //     // Login to Docker Registry
                //     sh 'echo "$REGISTRY_PASSWORD" | docker login -u "$REGISTRY_USER" --password-stdin "$REGISTRY_URL"'
                    
                //     // Pull the latest Docker image
                //     sh "docker pull \"$REGISTRY_INVENTORY_IMAGE:latest\""
                    
                //     // Copy environment file
                //     sh "cp \$ENV_FILE .env.${ENVIRONMENT}"

                //     echo 'Deploying to Staging'
                    
                //     // Use docker compose for deployment with explicit environment file
                //     sh """
                //         ENVIRONMENT=${ENVIRONMENT} \
                //         REGISTRY_URL=${REGISTRY_URL} \
                //         REGISTRY_INVENTORY_IMAGE=${REGISTRY_INVENTORY_IMAGE} \
                //         docker compose --env-file .env.${ENVIRONMENT} -f docker-compose.yml down
                //         docker compose pull
                //         docker compose --env-file .env.${ENVIRONMENT} -f docker-compose.yml up -d
                //     """
                    
                //     // Verify the containers are running
                //     sh '''
                //         echo "Verifying containers..."
                //         docker ps --format "table {{.Names}}\t{{.Status}}" | grep "INVENTORY-.*-development"
                //     '''
                    
                //     // Clean up unused images
                //     sh 'docker image prune -f'
                // }
            }
            // post {
            //     always {
            //         sh "rm -f .env.${ENVIRONMENT}"
            //         sh 'docker logout "$REGISTRY_URL"'
            //     }
            //     success {
            //         echo 'Deployment to Staging completed successfully'
            //         sh '''
            //             echo "Running containers:"
            //             docker ps --format "table {{.Names}}\t{{.Status}}" | grep "INVENTORY-.*-development"
            //         '''
            //     }
            //     failure {
            //         echo 'Deployment to Staging failed'
            //         sh '''
            //             echo "Container logs:"
            //             for container in $(docker ps -a --format "{{.Names}}" | grep "INVENTORY-.*-development"); do
            //                 echo "=== $container logs ==="
            //                 docker logs $container
            //             done
            //         '''
            //     }
            // }
        }
    }
}
