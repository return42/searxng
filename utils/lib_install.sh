#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later

# SEARX_SRC_INIT_FILES: array of file names to sync into a installation at
# $SEARX_SRC.  The file names arre relative to the $REPO_ROOT.  The inital ,
# value is set to the files which are modified in the local working-tree:
#  - .config.sh
#  - searx/settings.yml
#  - utils/brand.env
#  - ...

readarray -t SEARX_SRC_INIT_FILES < <(git diff --name-only)

eval orig_"$(declare -f source_dot_config)"
# orig_DOT_CONFIG="${DOT_CONFIG}"

source_dot_config() {
    # Modified source_dot_config function that monitores the files from
    # SEARX_SRC_INIT_FILES and loads .config.sh from an existing installation
    # (located at for SEARX_SRC).
    local msg=""
    if [ -z "$eval_SEARX_SRC" ]; then
        export eval_SEARX_SRC='true'
        SEARX_SRC=$("${REPO_ROOT}/utils/searx.sh" --getenv SEARX_SRC)

        # log monitored files if the local file is newer compared to the
        # corresponding file in the installation

        if [ -r "${SEARX_SRC}" ]; then
            for i in "${SEARX_SRC_INIT_FILES[@]}"; do
                if [[ "${REPO_ROOT}/$i" -nt "${SEARX_SRC}/$i" ]]; then
                    warn_msg "./$i "
                    msg="to update use:  sudo -H ./utils/searx.sh install init-src"
                fi
            done
        else
            info_msg "not yet cloned: ${SEARX_SRC}"
        fi

        # set and log DOT_CONFIG
        if [ -r "${SEARX_SRC}/.config.sh" ]; then
            warn_msg "ignoring config at: ${DOT_CONFIG}"
            info_msg "switching to ${SEARX_SRC}/.config.sh"
            DOT_CONFIG="${SEARX_SRC}/.config.sh"
        else
            info_msg "using local config: ${DOT_CONFIG}"
        fi
        if [ ! -z "$msg" ];then
            warn_msg "$msg"
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
