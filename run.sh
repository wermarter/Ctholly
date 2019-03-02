#!/usr/bin/env bash

# Assign install location to DIR
DIR=$(dirname "${BASH_SOURCE[0]}")

# Set terminal title
echo -en "\033]0;Ctholly\a"

# Run main.py in venv
source ${DIR}/venv/bin/activate
python ${DIR}/main.py