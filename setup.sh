#!/bin/bash
set -e

echo "=== Termux Environment Setup for Corpus Archive Tool ==="

echo "1. Requesting Android Storage Permission..."
termux-setup-storage

echo "2. Updating package lists and installing Python, Git & Git-LFS..."
echo "(Tip: If package updates fail, run 'termux-change-repo' to select a working mirror)"
pkg update -y
pkg install -y python git git-lfs

echo "3. Installing dependencies..."
pip install --upgrade huggingface_hub

echo ""
echo "=== Setup Completed Successfully! ==="
echo "You can now run:"
echo "  python ingest.py"
echo ""
