#!/bin/bash
set -e

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

wget -q https://storage.yandexcloud.net/cloud-certs/CA.pem -O YandexInternalRootCA.crt
echo "✓ SSL сертификат скачан"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Заполните .env перед запуском"
fi
