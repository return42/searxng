#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later

SEARX_SRC_INIT_FILES=(
    ".config.sh"
    "utils/brand.env"
)

eval orig_"$(declare -f source_dot_config)"
# orig_DOT_CONFIG="${DOT_CONFIG}"

source_dot_config() {
    # a modified source_dot_config function that looks for a file
    # /usr/local/searx/searx-src/
    local msg=""
    if [ -z "$eval_SEARX_SRC" ]; then
        export eval_SEARX_SRC='true'
        SEARX_SRC=$("${REPO_ROOT}/utils/searx.sh" --getenv SEARX_SRC)
        if [ -r "${SEARX_SRC}/.config.sh" ]; then
            info_msg "ignoring config at: ${DOT_CONFIG}"
            info_msg "switching to ${SEARX_SRC}/.config.sh"
            for i in "${SEARX_SRC_INIT_FILES[@]}"; do
                if [[ "${REPO_ROOT}/$i" -nt "${SEARX_SRC}/$i" ]]; then
                    warn_msg "${REPO_ROOT}/$i is newer!"
                    msg="to update use:  sudo -H ./utils/searx.sh install init-src"
                fi
            done
            if [ ! -z "$msg" ];then
                warn_msg "$msg"
            fi
            DOT_CONFIG="${SEARX_SRC}/.config.sh"
        else
            info_msg "using local config: ${DOT_CONFIG}"
        fi
    fi
    orig_source_dot_config
}

# shellcheck source=utils/brand.env
source "${REPO_ROOT}/utils/brand.env"

source_dot_config

# use PUBLIC_URL from .config.sh file
SEARX_URL="${PUBLIC_URL:-http://$(uname -n)/searx}"

# shellcheck source=utils/lxc-searx.env
source "${REPO_ROOT}/utils/lxc-searx.env"
in_container && lxc_set_suite_env
