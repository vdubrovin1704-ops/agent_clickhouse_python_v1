import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Anthropic
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192

# ClickHouse
CLICKHOUSE_HOST = os.environ["CLICKHOUSE_HOST"].replace("https://", "").replace("http://", "")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8443"))
CLICKHOUSE_USER = os.environ["CLICKHOUSE_USER"]
CLICKHOUSE_PASSWORD = os.environ["CLICKHOUSE_PASSWORD"]
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")

# SSL — поиск сертификата
CLICKHOUSE_SSL_CERT = ""
ssl_setting = os.environ.get("CLICKHOUSE_SSL_CERT_PATH", "")
if ssl_setting:
    cert = Path(ssl_setting)
    if not cert.is_absolute():
        cert = Path(__file__).parent / cert
    if cert.exists():
        CLICKHOUSE_SSL_CERT = str(cert.resolve())

# Пути
TEMP_DIR = Path(__file__).parent / "temp_data"
TEMP_DIR.mkdir(exist_ok=True)

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8000")
