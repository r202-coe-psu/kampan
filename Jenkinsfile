pipeline {
    agent { label 'mgmt' }

    // stages {
    //         stage('SonarQube Analysis') {
    //         when {
    //             anyOf {
    //                 branch 'develop'
    //                 branch 'main'
    //             }
    //         }
    //         steps {
    //             script {
    //                 def scannerHome = tool 'SonarScanner'
    //                 withCredentials([string(credentialsId: 'kampan_SONAR_TOKEN', variable: 'SONAR_TOKEN')]) {
    //                     withSonarQubeEnv() {
    //                         sh "${scannerHome}/bin/sonar-scanner -Dsonar.token=\$SONAR_TOKEN"
    //                     }
    //                 }
    //             }
    //         }
    //     }
        // stage('Deploy to Staging') {
        //     when {
        //         branch 'develop'
        //     }
        //     steps {
        //         withCredentials([
        //             sshUserPrivateKey(credentialsId: 'kampan-staging-ssh', keyFileVariable: 'SSH_KEY', usernameVariable: 'SSH_USER'),
        //             string(credentialsId: 'kampan-staging-host', variable: 'SSH_HOST'),
        //             string(credentialsId: 'kampan-staging-port', variable: 'SSH_PORT')
        //         ]) {
        //             sh '''
        //                 echo "Starting deployment to Staging server..."
                        
        //                 ssh -i $SSH_KEY -p $SSH_PORT -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST "
                            
        //                     echo '==> Deploying kampan Staging...'
        //                     cd /home/projects/kampan
        //                     git -C /home/projects/kampan fetch origin develop
        //                     git -C /home/projects/kampan checkout develop
        //                     git -C /home/projects/kampan reset --hard origin/develop
        //                     git -C /home/projects/kampan pull
        //                     docker compose -f docker-compose.staging.yml up -d --build --force-recreate

        //                 "
        //                 echo "Deployment process finished successfully!"
        //             '''
        //         }
        //     }
        // }

    stage('Deploy to Production') {
        when {
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
