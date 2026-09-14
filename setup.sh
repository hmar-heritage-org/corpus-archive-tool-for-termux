#!/bin/bash
set -e

echo "=== Termux Environment Setup for Corpus Archive Tool ==="

echo "1. Requesting Android Storage Permission..."
termux-setup-storage

echo "2. Updating package lists and installing Python & Git..."
pkg update -y
pkg install -y python git

echo "3. Installing huggingface_hub..."
pip install --upgrade huggingface_hub

echo ""
echo "=== Setup Completed Successfully! ==="
echo "You can now run:"
echo "  python ingest.py"
echo ""
