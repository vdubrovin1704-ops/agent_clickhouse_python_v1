#!/bin/bash
set -e

echo "=== Установка ClickHouse + Python Analysis Agent ==="

# Создать virtualenv
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install --upgrade pip
pip install -r requirements.txt

echo "✓ Python зависимости установлены"

# Скачать SSL сертификат для Яндекс Cloud ClickHouse
if [ ! -f YandexInternalRootCA.crt ]; then
    wget -q https://storage.yandexcloud.net/cloud-certs/CA.pem -O YandexInternalRootCA.crt
    echo "✓ SSL сертификат скачан: YandexInternalRootCA.crt"
else
    echo "✓ SSL сертификат уже существует"
fi

# Создать .env из шаблона если не существует
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  ВАЖНО: Отредактируйте файл .env и заполните:"
    echo "   - ANTHROPIC_API_KEY"
    echo "   - CLICKHOUSE_HOST"
    echo "   - CLICKHOUSE_USER"
    echo "   - CLICKHOUSE_PASSWORD"
    echo "   - CLICKHOUSE_DATABASE"
else
    echo "✓ Файл .env уже существует"
fi

# Создать директорию для временных файлов
mkdir -p temp_data

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Следующие шаги:"
echo "  1. Заполните .env файл (если ещё не заполнен)"
echo "  2. Активируйте virtualenv: source venv/bin/activate"
echo "  3. Запустите тест агента: python test_agent.py"
echo "  4. (Опционально) Запустите API сервер: uvicorn api_server:app --host 0.0.0.0 --port 8000"
