#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later

# https://github.com/koalaman/shellcheck/issues/356#issuecomment-853515285
# shellcheck source=utils/lib.sh
. /dev/null

# Initialize installation procedures:
#
# - Modified source_dot_config function that
#   - loads .config.sh from an existing installation (at SEARX_SRC).
#   - initialize **SEARX_SRC_INIT_FILES**
# - functions like:
#   - install_log_searx_instance()
#   - install_searx_get_state()
#
# usage:
#   source lib_install.sh
#
# **Installation scripts**
#
# The utils/lib_install.sh is sourced by the installations scripts:
#
# - utils/searx.sh
# - utils/morty.sh
# - utils/filtron.sh
#
# If '${SEARX_SRC}/.config.sh' exists, the modified source_dot_config() function
# loads this configuration (instead of './.config.sh').

# **SEARX_SRC_INIT_FILES**
#
# Array of file names to sync into a installation at $SEARX_SRC.  The file names
# are relative to the $REPO_ROOT.  Set by function init_SEARX_SRC_INIT_FILES().
# Most often theses are files like:
# - .config.sh
# - searx/settings.yml
# - utils/brand.env
# - ...


SEARX_SRC_INIT_FILES=()

eval orig_"$(declare -f source_dot_config)"

source_dot_config() {

    # Modified source_dot_config function that
    # - loads .config.sh from an existing installation (at SEARX_SRC).
    # - initialize SEARX_SRC_INIT_FILES

    if [ -z "$eval_SEARX_SRC" ]; then
        export eval_SEARX_SRC='true'
        SEARX_SRC=$("${REPO_ROOT}/utils/searx.sh" --getenv SEARX_SRC)
        if [ ! -r "${SEARX_SRC}" ]; then
            build_msg INSTANCE "not yet cloned: ${SEARX_SRC}"
            orig_source_dot_config
            return 0
        fi
        build_msg INSTANCE "using instance at: ${SEARX_SRC}"

        # set and log DOT_CONFIG
        if [ -r "${SEARX_SRC}/.config.sh" ]; then
            build_msg INSTANCE "switching to ${SEARX_SRC}/.config.sh"
            DOT_CONFIG="${SEARX_SRC}/.config.sh"
        else
            build_msg INSTANCE "using local config: ${DOT_CONFIG}"
        fi
        init_SEARX_SRC_INIT_FILES
    fi
}

init_SEARX_SRC_INIT_FILES(){
    # init environment SEARX_SRC_INIT_FILES

    # Monitor modified files in the working-tree from the local repository, only
    # if the local file differs to the corresponding file in the instance.  Most
    # often theses are files like:
    #
    #  - .config.sh
    #  - searx/settings.yml
    #  - utils/brand.env
    #  - ...

    # keep list empty if there is no installation
    SEARX_SRC_INIT_FILES=()
    if [ ! -r "$SEARX_SRC" ]; then
        return 0
    fi

    local fname
    local msg=""

    # Monitor local modified files from the repository, only if the local file
    # differs to the corresponding file in the instance

    while IFS= read -r fname; do
        if [ -z "$fname" ]; then
            continue
        fi
        if [ -r "${SEARX_SRC}/${fname}" ]; then
            # diff  "${REPO_ROOT}/${fname}" "${SEARX_SRC}/${fname}"
            if ! cmp --silent "${REPO_ROOT}/${fname}" "${SEARX_SRC}/${fname}"; then
                SEARX_SRC_INIT_FILES+=("${fname}")
                build_msg INSTANCE "local clone (workingtree), modified file: ./$fname"
                msg="to update use:  sudo -H ./utils/searx.sh install init-src"
            fi
        fi
    done <<< "$(git diff --name-only)"
    [ -n "$msg" ] &&  build_msg INSTANCE "$msg"
}

install_log_searx_instance() {

    echo -e "---- SearXNG instance setup ${_BBlue}(status: $(install_searx_get_state))${_creset}"
    echo -e "  SEARX_SETTINGS_PATH : ${_BBlue}${SEARX_SETTINGS_PATH}${_creset}"
    echo -e "  SEARX_SRC           : ${_BBlue}${SEARX_SRC:-none}${_creset}"
    echo -e "  SEARX_URL           : ${_BBlue}${SEARX_URL:-none}${_creset}"

    if in_container; then
        # searx is listening on 127.0.0.1 and not available from outside container
        # in containers the service is listening on 0.0.0.0 (see lxc-searx.env)
        echo -e "---- container setup"
        echo -e "  ${_BBlack}HINT:${_creset} searx only listen on loopback device" \
             "${_BBlack}inside${_creset} the container."
        for ip in $(global_IPs) ; do
            if [[ $ip =~ .*:.* ]]; then
                echo "  container (IPv6): [${ip#*|}]"
            else
                # IPv4:
                echo "  container (IPv4): ${ip#*|}"
            fi
        done
    fi
}

install_searx_get_state(){

    # usage: install_searx_get_state
    #
    # Prompts a string indicating the status of the installation procedure
    #
    # missing-searx-clone:
    #    There is no clone at ${SEARX_SRC}
    # missing-searx-pyenv:
    #    There is no pyenv in ${SEARX_PYENV}
    # installer-modified:
    #    There are files modified locally in the installer (clone),
    #    see ${SEARX_SRC_INIT_FILES} description.
    # python-installed:
    #    Scripts can be executed in instance's environment
    #    - user:  ${SERVICE_USER}
    #    - pyenv: ${SEARX_PYENV}

    if ! [ -r "${SEARX_SRC}" ]; then
        echo "missing-searx-clone"
        return
    fi
    if ! [ -f "${SEARX_PYENV}/bin/activate" ]; then
        echo "missing-searx-pyenv"
        return
    fi
    if ! [ -r "${SEARX_SETTINGS_PATH}" ]; then
        echo "missing-settings"
        return
    fi
    if ! [ ${#SEARX_SRC_INIT_FILES[*]} -eq 0 ]; then
        echo "installer-modified"
        return
    fi
    echo "python-installed"
}

# Initialization of the installation procedure
# --------------------------------------------

# shellcheck source=utils/brand.env
source "${REPO_ROOT}/utils/brand.env"

source_dot_config

# shellcheck source=utils/lxc-searx.env
source "${REPO_ROOT}/utils/lxc-searx.env"
in_container && lxc_set_suite_env
