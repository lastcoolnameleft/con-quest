#!/bin/bash
set -e

echo "Pushing env files to dh:con-quest..."
scp .env.stg dh:con-quest/
scp .env.prod dh:con-quest/
echo "Done."
