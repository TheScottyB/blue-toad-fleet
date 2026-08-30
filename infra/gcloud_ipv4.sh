# Force IPv4 for gcloud/Python. On some paths (T-Mobile IPv6, AAAA-first
# Python) API gcloud hangs in SYN_SENT to Google; local commands do not.
# Recreate the sitecustomize so a wiped TMPDIR still deploys.
#
# gcloud's wrapper adds `python -S` unless CLOUDSDK_PYTHON_SITEPACKAGES or a
# virtenv is set; -S skips sitecustomize. Export the flag so PYTHONPATH is
# actually imported.
# shellcheck shell=bash
_BTF_GCLOUD_IPV4="${TMPDIR:-/tmp}"
_BTF_GCLOUD_IPV4="${_BTF_GCLOUD_IPV4%/}/gcloud-ipv4"
mkdir -p "$_BTF_GCLOUD_IPV4"
cat > "$_BTF_GCLOUD_IPV4/sitecustomize.py" <<'PY'
import socket
_orig = socket.getaddrinfo
def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family in (0, socket.AF_UNSPEC):
        family = socket.AF_INET
    return _orig(host, port, family, type, proto, flags)
socket.getaddrinfo = getaddrinfo
PY
export PYTHONPATH="${_BTF_GCLOUD_IPV4}${PYTHONPATH:+:$PYTHONPATH}"
export CLOUDSDK_PYTHON_SITEPACKAGES=1
