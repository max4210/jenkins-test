pipeline {
    agent any

    triggers {
        pollSCM('H/5 * * * *')
        cron('H 2 * * *')
    }

    parameters {
        string(name: 'CML_URL', defaultValue: 'https://192.168.137.125',
               description: 'CML server URL')
        string(name: 'LAB_TITLE', defaultValue: 'Jenkins-Terraform-Lab',
               description: 'Name for the CML lab')
    }

    environment {
        CML_CREDENTIALS = credentials('cml-credentials')
        CML_URL         = "${params.CML_URL}"
        CML_USERNAME    = "${CML_CREDENTIALS_USR}"
        CML_PASSWORD    = "${CML_CREDENTIALS_PSW}"
        TF_VAR_cml_url  = "${params.CML_URL}"
        TF_VAR_cml_username = "${CML_CREDENTIALS_USR}"
        TF_VAR_cml_password = "${CML_CREDENTIALS_PSW}"
        TF_VAR_lab_title    = "${params.LAB_TITLE}"
        TF_IN_AUTOMATION    = 'true'
    }

    options {
        timestamps()
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Validate') {
            steps {
                sh '''
                    nac-validate -s .schema.yaml -r .rules data/
                '''
            }
        }

        stage('Terraform Init') {
            steps {
                dir('terraform') {
                    sh 'terraform init -input=false'
                }
            }
        }

        stage('Terraform Plan') {
            steps {
                dir('terraform') {
                    sh 'terraform plan -input=false -out=tfplan'
                }
            }
        }

        stage('Terraform Apply') {
            steps {
                dir('terraform') {
                    sh 'terraform apply -input=false -auto-approve tfplan'
                }
            }
        }
    }

    post {
        success {
            echo 'Pipeline completed - CML lab deployed successfully.'
        }
        failure {
            echo 'Pipeline failed - check logs. Lab may persist for debugging.'
        }
    }
}
