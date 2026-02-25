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

        stage('Validate: Schema') {
            steps {
                echo '=========================================='
                echo '  STEP 1/3 — Schema Validation (Yamale)'
                echo '=========================================='
                echo 'Checks every data/*.nac.yaml against .schema.yaml:'
                echo '  - Required keys present (hostname, type, ...)'
                echo '  - Value types correct (str, int, bool, list)'
                echo '  - Value ranges enforced (VLAN 1-4094, hostname max 63 chars)'
                echo '  - Nested structures match definitions (ospf, wireless, ...)'
                echo ''
                sh '''
                    echo "Data files:"
                    ls -1 data/*.nac.yaml
                    echo ""
                    nac-validate -s .schema.yaml data/
                '''
            }
        }

        stage('Validate: Rules') {
            steps {
                echo '=========================================='
                echo '  STEP 2/3 — Semantic Rules (per-file)'
                echo '=========================================='
                echo 'Runs Python rules from .rules/ against each data file:'
                echo '  101  Unique VLAN IDs within a device'
                echo '  102  All IPs are valid IPv4 format'
                echo '  103  Subnet masks are contiguous'
                echo '  104  OSPF router-ID matches loopback IP'
                echo '  105  Unique WLAN IDs and SSIDs'
                echo '  106  Policy tag mappings reference existing WLANs/profiles'
                echo '  107  Referenced VLANs exist in the vlans list'
                echo '  108  WLAN security type is a recognized value'
                echo '  109  Hostname is RFC 1123 compliant'
                echo '  110  Routed interfaces have IP or DHCP'
                echo ''
                sh '''
                    echo "Rules:"
                    ls -1 .rules/*.py
                    echo ""
                    nac-validate -r .rules data/
                '''
            }
        }

        stage('Validate: Cross-file') {
            steps {
                echo '=========================================='
                echo '  STEP 3/3 — Cross-file Consistency'
                echo '=========================================='
                echo 'Loads all data files together and checks:'
                echo '  - OSPF router-IDs unique across devices'
                echo '  - Loopback IPs unique across devices'
                echo '  - No duplicate IPs anywhere'
                echo '  - WLC management subnet matches switch SVI'
                echo '  - WLC VLANs exist on switch and are allowed on trunk'
                echo '  - OSPF network statements cover loopback addresses'
                echo ''
                sh 'python3 scripts/cross_validate.py data/'
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
                        echo "Removing all tracked resources from state..."
                        terraform state list 2>/dev/null | while read -r resource; do
                            echo "  removing: $resource"
                            terraform state rm "$resource" 2>/dev/null || true
                        done
                    '''
                }
                echo 'Terraform state cleared — next plan will create resources from scratch.'
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
            echo 'Pipeline completed — CML lab deployed successfully.'
        }
        failure {
            echo 'Pipeline FAILED — check stage logs above. Lab may persist for debugging.'
        }
    }
}
