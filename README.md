# zpod-template-generator

A standalone CLI tool that fetches zPod metadata from the zpodapi and renders Jinja2 templates with that data. Useful for generating configuration files, documentation, or scripts tailored to a specific zPod deployment.

This script has been vibe code with Claude Code for fun.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (no manual dependency install needed)

## Quick Start

### 1. Configure API access

Copy the sample env file and fill in your values:

```bash
cp .env.sample .env
```

```env
ZPODFACTORY_HOST=http://zpodfactory.fqdn.com:8000
ZPODFACTORY_TOKEN=your_api_token_here
```

### 2. List available zPods

```bash
uv run zpod-template-generator.py --list-zpods
```

### 3. Render a template

```bash
$ uv run zpod-template-generator.py \
  --zpod-name demo \
  --template-file templates/summary.j2


Fetching zPod 'demo' from http://172.16.42.11:8300...
Fetching DNS entries for zPod id=423...
Fetching zPodFactory settings...
## zPod Informations

zPod: demo
Domain: demo.zpodfactory.io
Status: ACTIVE
Profile: proxmox
Password: lseoTs6hM!bxvzyu
# You can index directly an object to fetch it's value (zpod_networks[0].cidr)
Management Network: 10.196.130.0/26 

$
```

Write output to a file instead of stdout:

```bash
$ uv run zpod-template-generator.py \
  --zpod-name demo \
  --template-file templates/components.j2 \
  --output-file /tmp/plop.txt

Fetching zPod 'demo' from http://172.16.42.11:8300...
Fetching DNS entries for zPod id=423...
Fetching zPodFactory settings...
Output written to /tmp/plop.txt

$ cat /tmp/plop.txt

# Components for zPod: demo
- zbox 12.11 | 10.196.130.2 | zbox.demo.zpodfactory.io
- proxmox 9.1.4 | 10.196.130.11 | prox11.demo.zpodfactory.io
- proxmox 9.1.4 | 10.196.130.12 | prox12.demo.zpodfactory.io
- proxmox 9.1.4 | 10.196.130.13 | prox13.demo.zpodfactory.io
- proxmox-dm 1.0.2-dev | 10.196.130.20 | proxmgr.demo.zpodfactory.io
- proxmox-bs 4.1-dev | 10.196.130.49 | proxbkp.demo.zpodfactory.io

$
```

### 4. Use extra variables

Pass extra variables via a JSON file with `--extra-vars`:

Example `extra-vars/sample.json`:

```json
{
  "username": "zadmin",
  "password": "supersecret",
  "version": 13.3
}
```

Added at the end of the `summary-with-extra-vars.j2` template

```jinja2
## --- Extra Variables ---
## Extra variables from --extra-vars are available by their key names.

EXTRA VARS Username: {{ username }}
EXTRA VARS Password: {{ password }}
EXTRA VARS Version:  {{ version }}
```


```bash
$ uv run zpod-template-generator.py \
  --zpod-name demo \
  --template-file templates/summary-with-extra-vars.j2 \
  --extra-vars extra-vars/sample.json

Fetching zPod 'demo' from http://172.16.42.11:8300...
Fetching DNS entries for zPod id=423...
Fetching zPodFactory settings...
## zPod Informations

zPod: demo
Domain: demo.zpodfactory.io
Status: ACTIVE
Profile: proxmox
Password: lseoTs6hM!bxvzyu
# You can index directly an object to fetch it's value (zpod_networks[0].cidr)
Management Network: 10.196.130.0/26

## --- Extra Variables ---
## Extra variables from --extra-vars are available by their key names.

EXTRA VARS Username: zadmin
EXTRA VARS Password: supersecret
EXTRA VARS Version:  13.3

$
```


## CLI Reference

```
uv run zpod-template-generator.py --help
```

| Option | Env Var | Description |
|---|---|---|
| `--zpodfactory-host` | `ZPODFACTORY_HOST` | zpodapi host URL |
| `--zpodfactory-token` | `ZPODFACTORY_TOKEN` | zpodapi access token |
| `--list-zpods` | | List available zPods and exit |
| `--zpod-name` | | Name of the zPod to fetch |
| `--template-file` | | Path to the Jinja2 template file |
| `--extra-vars` | | Path to a JSON file with extra template variables |
| `--output-file` | | Write output to file instead of stdout |

## Template Variables

### zPod fields

| Variable | Example |
|---|---|
| `zpod_name` | `demo` |
| `zpod_description` | `Demo zPod` |
| `zpod_domain` | `demo.maindomain.com` |
| `zpod_password` | `yZnqji!a4xbo` |
| `zpod_profile` | `sddc` |
| `zpod_status` | `ACTIVE` |
| `zpod_creation_date` | `2023-01-01T00:00:00` |
| `zpod_last_modified_date` | `2023-01-01T00:00:00` |

### Computed network/infrastructure values

Derived from the management network CIDR, zbox component, and zPodFactory settings:

| Variable | Description | Example |
|---|---|---|
| `zpod_subnet` | First three octets of the management network | `10.196.130` |
| `zpod_gateway` | Gateway IP (first usable host in mgmt network) | `10.196.130.1` |
| `zpod_netmask` | Netmask of the management network | `255.255.255.192` |
| `zpod_netprefix` | Prefix length of the management network | `26` |
| `zpod_portgroup` | Port group name (`zpod-{name}-segment`) | `zpod-demo-segment` |
| `zpod_dns` | DNS server IP (zbox component) | `10.196.130.2` |
| `zpod_nfs` | NFS server IP (zbox component) | `10.196.130.2` |
| `zpod_ntp` | NTP server IP (from `zpodfactory_host` setting) | `172.16.42.11` |
| `zpod_sshkey` | SSH public key (from `zpodfactory_ssh_key` setting) | `ssh-rsa AAAA...` |

### Collections (for iteration)

| Variable | Description |
|---|---|
| `zpod_components` | List of component dicts |
| `zpod_networks` | List of network dicts |
| `zpod_dns_records` | List of DNS entry dicts (`ip`, `hostname`) |
| `zpod_endpoint` | Endpoint dict (`name`, `status`) |
| `zpod_features` | Features dict |
| `zpod_settings` | List of setting dicts (`name`, `description`, `value`) |
| `zpod_permissions` | List of permission dicts |

### Convenience shortcuts

Individual components are accessible by name:

```jinja2
{% if zpod_component_vcsa is defined %}
vCSA IP: {{ zpod_component_vcsa.ip }}
{% endif %}
```

Individual settings are accessible by name (value only):

```jinja2
Domain: {{ zpod_setting_zpodfactory_default_domain }}
```

## Sample Templates

| Template | Description |
|---|---|
| `templates/summary.j2` | Basic zPod info (name, domain, status, profile, password) |
| `templates/summary-with-extra-vars.j2` | Same as above but with extra vars support | 
| `templates/dns-hosts.j2` | `/etc/hosts` format entries from zPod DNS |
| `templates/components.j2` | Component list with IP and FQDN |
| `templates/example.j2` | Comprehensive example showing all available variables |
