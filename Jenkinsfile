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
        string(name: 'WLC_NODE_DEFINITION', defaultValue: 'cat9800',
               description: 'CML node for WLC: cat9800 or iosv (fallback)')
        booleanParam(name: 'RESET_STATE', defaultValue: false,
               description: 'Clear Terraform state (use when lab was deleted outside Terraform, e.g. 404 Lab not found)')
    }

    environment {
        CML_CREDENTIALS     = credentials('cml-credentials')
        DEVICE_CREDENTIALS  = credentials('device-credentials')
        CML_URL             = "${params.CML_URL}"
        CML_USERNAME        = "${CML_CREDENTIALS_USR}"
        CML_PASSWORD        = "${CML_CREDENTIALS_PSW}"
        TF_VAR_cml_url      = "${params.CML_URL}"
        TF_VAR_cml_username = "${CML_CREDENTIALS_USR}"
        TF_VAR_cml_password = "${CML_CREDENTIALS_PSW}"
        TF_VAR_lab_title    = "${params.LAB_TITLE}"
        TF_VAR_wlc_node_definition = "${params.WLC_NODE_DEFINITION}"
        TF_VAR_device_username = "${DEVICE_CREDENTIALS_USR}"
        TF_VAR_device_password = "${DEVICE_CREDENTIALS_PSW}"
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

        stage('Reset State') {
            when {
                expression { return params.RESET_STATE }
            }
            steps {
                dir('terraform') {
                    sh '''
                        terraform state rm cml2_lifecycle.network_lab cml2_link.router_to_switch cml2_link.wlc_to_switch cml2_node.router cml2_node.switch cml2_node.wlc cml2_lab.network_lab 2>/dev/null || true
                    '''
                }
                echo 'Terraform state cleared - next plan will create resources from scratch.'
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
