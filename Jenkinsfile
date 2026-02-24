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
        CML_CREDENTIALS   = credentials('cml-credentials')
        CML_URL            = "${params.CML_URL}"
        CML_USERNAME       = "${CML_CREDENTIALS_USR}"
        CML_PASSWORD       = "${CML_CREDENTIALS_PSW}"
        DEVICE_USERNAME    = 'admin'
        DEVICE_PASSWORD    = 'admin'
        TF_VAR_cml_url     = "${params.CML_URL}"
        TF_VAR_cml_username = "${CML_CREDENTIALS_USR}"
        TF_VAR_cml_password = "${CML_CREDENTIALS_PSW}"
        TF_VAR_lab_title    = "${params.LAB_TITLE}"
        TF_IN_AUTOMATION    = 'true'
    }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
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

        stage('Extract Lab ID') {
            steps {
                dir('terraform') {
                    script {
                        env.LAB_ID = sh(
                            script: 'terraform output -raw lab_id',
                            returnStdout: true
                        ).trim()
                    }
                }
                echo "CML Lab ID: ${env.LAB_ID}"
            }
        }

        stage('Generate Testbed') {
            steps {
                sh """
                    python3 scripts/generate_testbed.py \
                        --tf-dir terraform \
                        --output tests/testbed.yaml
                """
                sh 'cat tests/testbed.yaml'
            }
        }

        stage('Run pyATS Tests') {
            steps {
                sh """
                    pyats run job tests/test_basic.py \
                        --testbed-file tests/testbed.yaml \
                        --html-logs pyats_logs \
                        --no-archive
                """
            }
            post {
                always {
                    archiveArtifacts artifacts: 'pyats_logs/**', allowEmptyArchive: true
                    junit testResults: '**/pyats_junit.xml', allowEmptyResults: true
                }
            }
        }
    }

    post {
        always {
            echo 'Cleaning up CML lab ...'
            dir('terraform') {
                sh 'terraform destroy -input=false -auto-approve || true'
            }
        }
        success {
            echo 'Pipeline completed successfully - all pyATS tests passed.'
        }
        failure {
            echo 'Pipeline failed - check logs for details.'
        }
    }
}
