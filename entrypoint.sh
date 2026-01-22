#!/bin/bash

set -o errexit
set -o nounset
set -o pipefail

echo "Starting AI SDK"
python run.py both --no-logs