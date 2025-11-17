#!/usr/bin/env python3
"""
Dynamic Inventory Script for AAP Patching (ServiceNow-defined Patch Groups)
------------------------------------------------------------------------
- Pulls host data from ServiceNow CMDB
- Filters hosts based on OS, state, install_status, ignore lists
- Groups hosts exactly as defined in ServiceNow u_patching_group
- Outputs Ansible-compatible JSON inventory
- Debug logs go to STDERR
"""

import argparse
import sys
import socket
import json
import requests

# -------------------------------
# CONFIGURATION / GLOBAL VARIABLES
# -------------------------------
IGNORE_HOSTS = ["drhost01", "backup01"]           # Hosts to ignore completely
IGNORE_GROUPS = ["unix_team", "do_not_patch"]    # Groups to ignore
SUPPORTED_OSES = ["Linux%20Red%20Hat"]           # Allowed OS strings
MAX_HOSTS = 15000                                 # Default ServiceNow limit

# -----------------------------------
# HELPER FUNCTIONS
# -----------------------------------

def debug_print(msg, debug=False):
    """Print debug messages to STDERR if debug is enabled."""
    if debug:
        print(f"[DEBUG] {msg}", file=sys.stderr)

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Dynamic Inventory for Patching")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--limit", type=int, default=MAX_HOSTS)
    parser.add_argument("--os-filter", type=str, default=SUPPORTED_OSES[0])
    return parser.parse_args()

def servicenow_query(os_filter, limit):
    """
    Call ServiceNow API to retrieve host data.
    Credentials can be stored outside Git (environment, Tower custom credential).
    """
    instance = "your_instance"
    user = "your_user"
    pwd = "your_password"
    url = f"https://{instance}.service-now.com/api/now/table/cmdb_ci_server"
    query = f"?sysparm_query=os={os_filter}^install_status=1^state=Live&sysparm_limit={limit}"

    try:
        response = requests.get(url + query, auth=(user, pwd), timeout=30)
        response.raise_for_status()
        data = response.json().get("result", [])
        return data
    except Exception as e:
        print(f"[ERROR] ServiceNow query failed: {e}", file=sys.stderr)
        sys.exit(1)

def ignore_host(host):
    """Return True if host should be ignored based on hostname or patch group."""
    hname = host.get("name", "").lower()
    group = host.get("u_patching_group", "").lower()
    return hname in IGNORE_HOSTS or group in IGNORE_GROUPS or not group

def resolve_dns(hostname, domain="example.com"):
    """Resolve DNS, return dict with hostname, IP, and validity."""
    try:
        if "." not in hostname:
            hostname = f"{hostname}.{domain}"
        ip = socket.gethostbyname(hostname)
        return {"hostname": hostname, "ip": ip, "valid": True}
    except Exception:
        return {"hostname": hostname, "ip": None, "valid": False}

def distribute_hosts(all_hosts):
    """
    Group hosts by ServiceNow-defined patch group.
    Returns a dictionary with patch_group as keys and host lists as values.
    """
    groups = {}
    for h in all_hosts:
        group_name = h["u_patching_group"]
        groups.setdefault(group_name, []).append(h["name"])
    return groups

def build_ansible_inventory(distribution):
    """
    Build final Ansible inventory JSON from distribution dictionary.
    Adds all hosts under "all" key.
    """
    inventory = {"all": {"hosts": []}}
    for group, hosts in distribution.items():
        inventory[group] = {"hosts": hosts}
        inventory["all"]["hosts"].extend(hosts)
    return inventory

def print_inventory(inventory):
    """Print final JSON inventory to STDOUT."""
    json.dump(inventory, sys.stdout, indent=2)

# -------------------------------
# MAIN FUNCTION
# -------------------------------
def main():
    args = parse_args()
    debug = args.debug

    debug_print("Starting Dynamic Inventory Script...", debug)

    # Query ServiceNow CMDB
    raw_hosts = servicenow_query(os_filter=args.os_filter, limit=args.limit)
    debug_print(f"Retrieved {len(raw_hosts)} hosts from ServiceNow.", debug)

    filtered_hosts = []

    # Filter hosts and validate DNS
    for rec in raw_hosts:
        hostname = rec.get("name")
        patch_group = rec.get("u_patching_group")

        if ignore_host(rec):
            debug_print(f"Ignoring host: {hostname}", debug)
            continue

        dns_info = resolve_dns(hostname)
        if not dns_info["valid"]:
            debug_print(f"Dropping host due to DNS failure: {hostname}", debug)
            continue

        filtered_hosts.append(rec)

    debug_print(f"Total hosts after filtering: {len(filtered_hosts)}", debug)

    # Group hosts by ServiceNow patch group
    distribution = distribute_hosts(filtered_hosts)
    debug_print(f"Hosts grouped by patch group: {list(distribution.keys())}", debug)

    # Build Ansible JSON inventory
    inventory = build_ansible_inventory(distribution)
    debug_print("Inventory generation complete.", debug)

    # Print inventory to STDOUT
    print_inventory(inventory)

# -------------------------------
# ENTRY POINT
# -------------------------------
if __name__ == "__main__":
    main()
