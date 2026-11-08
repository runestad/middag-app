#!/bin/sh
set -eu
# Deploy the browser app only. Recipe backups and recovery data are served by
# authenticated API handlers, and historical app versions stay out of the site.
mkdir -p dist
cp index.html delt.html eier.html *.js *.css manifest.webmanifest favicon.png dist/
cp -R assets icons dist/
