#!/bin/bash
set -e

echo "=== Установка ClickHouse + Python Analysis Agent ==="

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install --upgrade pip
pip install -r requirements.txt

# Скачать SSL сертификат для Яндекс Cloud
wget -q https://storage.yandexcloud.net/cloud-certs/CA.pem -O YandexInternalRootCA.crt
echo "✓ SSL сертификат скачан"

# Создать .env из шаблона если не существует
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Создан .env из шаблона. Отредактируйте его и заполните данные."
else
    echo "✓ .env уже существует"
fi

# Создать директорию для временных файлов
mkdir -p temp_data

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Следующие шаги:"
echo "  1. Отредактируйте .env — укажите ANTHROPIC_API_KEY и данные ClickHouse"
echo "  2. Тест:   source venv/bin/activate && python test_agent.py"
echo "  3. Сервер: source venv/bin/activate && uvicorn api_server:app --host 0.0.0.0 --port 8000"
