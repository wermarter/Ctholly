#!/usr/bin/env bash

# Add `alias ctholly=${PATH_TO_RUN.SH}` to `.bashrc`
# will allow you to use Ctholly via `ctholly` in terminal

# Assign install location to DIR
DIR=$(dirname "${BASH_SOURCE[0]}")

# Set terminal title
echo -en "\033]0;Ctholly\a"

# Run main.py in venv
source ${DIR}/venv/bin/activate
python ${DIR}/main.py