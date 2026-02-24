# NAC-Style CI/CD for CML 2.9

NetAsCode-style CI/CD pipeline: YAML configuration repository for 9800 WLC, switch, and router with data/code separation, nac-validate for validation, and Terraform deployment to CML 2.9.

## Architecture

```
GitHub Push / Manual / Schedule
        |
        v
   +-----------+
   |  Jenkins   |
   +-----------+
        |
   1. nac-validate (schema + rules)
   2. terraform plan
   3. terraform apply
        |
        v
   CML 2.9 (192.168.137.125)
   Lab: router + switch + wlc
```

## Project Structure

```
.
├── docker-compose.yml       # Jenkins Docker setup
├── Dockerfile.jenkins       # Jenkins + Terraform + nac-validate
├── Jenkinsfile              # Pipeline: Validate -> Plan -> Apply
├── .schema.yaml             # Yamale schema for config validation
├── .rules/                  # Custom semantic rules (Python)
│   └── example_rule.py
├── data/                    # Configuration data (separate from code)
│   ├── router.nac.yaml
│   ├── switch.nac.yaml
│   └── wlc_9800.nac.yaml
├── terraform/
│   ├── main.tf              # CML2 provider, lab + nodes + lifecycle
│   ├── config_inject.tf     # Read YAML, build node configs
│   ├── variables.tf
│   └── outputs.tf
└── README.md
```

## Data vs Code Separation

| Layer   | Location           | Purpose                                      |
|---------|--------------------|----------------------------------------------|
| **Data**| `data/*.nac.yaml`  | Device config (hostname, IPs, interfaces, VLANs, SSIDs) |
| **Credentials** | Jenkins `device-credentials` | Device login (never in repo)        |
| **Schema** | `.schema.yaml`  | Allowed keys, types, constraints             |
| **Rules** | `.rules/*.py`   | Business logic (e.g., unique VLAN IDs)       |
| **Code** | `terraform/`, `Jenkinsfile` | Deployment logic                    |

## Quick Start

### 1. Start Jenkins

```bash
docker-compose up -d --build
```

Jenkins: http://localhost:8080

### 2. Configure Jenkins

Add two credentials (**Manage Jenkins** > **Credentials** > Add **Username with password**):

- **CML API**: ID `cml-credentials` – username/password for CML server
- **Device login**: ID `device-credentials` – username/password for router/switch/WLC (e.g. admin/admin for lab)

### 3. Create Pipeline Job

- **New Item** > name: `nac-cml-pipeline` > **Pipeline**
- **Pipeline** > Definition: **Pipeline script from SCM**
- SCM: **Git** > Repo URL, Credentials, Branch: `*/main`
- Script Path: `Jenkinsfile`

### 4. Edit Configuration

Edit `data/*.nac.yaml` and push to GitHub. The pipeline will:

1. Validate YAML against schema and rules
2. Plan Terraform changes
3. Apply to CML 2.9 at 192.168.137.125

## Local Validation

```bash
pip install nac-validate
nac-validate -s .schema.yaml -r .rules data/
```

## Local Terraform

```bash
export TF_VAR_cml_username="your-cml-user"
export TF_VAR_cml_password="your-cml-password"
export TF_VAR_device_username="admin"
export TF_VAR_device_password="admin"
cd terraform
terraform init
terraform plan
terraform apply
```

## CML Topology

- **router** (iosv) – connects to switch
- **switch** (iosvl2) – connects router and WLC
- **wlc** (iosv by default; set `TF_VAR_wlc_node_definition=C9800-CL` if licensed)

## Triggers

- **pollSCM**: Every 5 minutes
- **cron**: Nightly at ~2 AM
- **Manual**: Build with Parameters
