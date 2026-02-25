# NAC-Style CI/CD for CML 2.9

NetAsCode-style CI/CD pipeline: YAML configuration repository for C9800 WLC, switch, and router with data/code separation, nac-validate for validation, and Terraform deployment to CML 2.9.

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
   Lab: router + switch + C9800 WLC + bridge0
```

## Network Design

```
                    [External Connector bridge0]
                              |
                    [Unmanaged Switch (mgmt-hub)]
                    /          |          \
           Router Gi0/1  Switch Gi0/2   WLC Gi2    (DHCP)
              |                |             |
           Router Gi0/0 --- Switch Gi0/0  (VLAN 10 - access)
                             Switch Gi0/1 --- WLC Gi1  (trunk: VLAN 20,100,200)
```

| VLAN | Name       | Subnet         | Purpose                     |
|------|------------|----------------|-----------------------------|
| 1    | default    | DHCP (bridge0) | OOB management              |
| 10   | DATA       | 10.0.10.0/24   | Router-Switch transit       |
| 20   | WLC-MGMT   | 10.0.20.0/24   | WLC management / OSPF       |
| 100  | CORPORATE  | 10.0.100.0/24  | Corporate SSID clients      |
| 200  | GUEST      | 10.0.200.0/24  | Guest SSID clients          |

### OSPF Area 0

All three devices run OSPF 1 with `passive-interface default` and explicit active neighbors:

| Device | Router-ID | Loopback   | Active Interfaces |
|--------|-----------|------------|-------------------|
| R1     | 1.1.1.1   | Lo0 1.1.1.1/32 | Gi0/0         |
| SW1    | 2.2.2.2   | Lo0 2.2.2.2/32 | Vlan10, Vlan20|
| WLC1   | 3.3.3.3   | Lo0 3.3.3.3/32 | Vlan20        |

### C9800 Wireless

| WLAN        | ID | Security       | VLAN | Policy Profile |
|-------------|----|----------------|------|----------------|
| Corporate   | 1  | WPA2-Personal  | 100  | pp-corporate   |
| Guest-WiFi  | 2  | Open           | 200  | pp-guest       |

Policy tag `pt-default` maps both WLANs to their policy profiles.

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
│   ├── main.tf              # CML2 provider, lab + nodes + links + lifecycle
│   ├── config_inject.tf     # Read YAML, build IOS-XE / C9800 day-0 configs
│   ├── variables.tf
│   └── outputs.tf
└── README.md
```

## Data vs Code Separation

| Layer   | Location           | Purpose                                      |
|---------|--------------------|----------------------------------------------|
| **Data**| `data/*.nac.yaml`  | Device config (hostname, VLANs, OSPF, wireless, IPs) |
| **Credentials** | Jenkins `device-credentials` | Device login + WPA PSK (never in repo) |
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

- **CML API**: ID `cml-credentials` -- username/password for CML server
- **Device login**: ID `device-credentials` -- username/password for router/switch/WLC (also used as WPA2 PSK in lab)

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

## Prerequisites

- CML 2.9 with `bridge0` configured on the host (connects lab to external network / DHCP)
- CML node definitions: `iosv`, `iosvl2`, `cat9800`, `external_connector`, `unmanaged_switch`

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

- **bridge0** (external_connector) -- external network access via bridge0
- **mgmt-hub** (unmanaged_switch) -- fans out bridge0 to all devices
- **router** (iosv) -- Gi0/0 to switch, Gi0/1 to mgmt-hub (DHCP)
- **switch** (iosvl2) -- L3 switch, OSPF, trunks to WLC, Gi0/2 to mgmt-hub (DHCP)
- **wlc** (cat9800) -- C9800-CL, Gi1 trunk to switch, Gi2 to mgmt-hub (DHCP)

## Triggers

- **pollSCM**: Every 5 minutes
- **cron**: Nightly at ~2 AM
- **Manual**: Build with Parameters

## Troubleshooting

**"Lab not found" (404)** -- The lab was deleted outside Terraform. Run **Build with Parameters**, set **RESET_STATE** to `true`, then build.

**WLC slot mapping** -- If your CML `cat9800` node definition maps interfaces differently (e.g., Gi0 instead of Gi1 for slot 0), update `trunk_interface` and `mgmt_dhcp_interface` in `data/wlc_9800.nac.yaml`.
