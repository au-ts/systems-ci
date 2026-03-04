# Run this with 'source' unless you support GITHUB_ENV

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

set_env_var() {
    name=$1
    value=$2

    export ${name}=${value}

    if [[ ${GITHUB_ENV} ]]; then
        echo "${name}=${value}" >> ${GITHUB_ENV}
    fi
}

set_env_var PYTHONPATH "$SCRIPT_DIR:$PYTHONPATH"
