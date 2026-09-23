FROM python:3.14-slim-bookworm

# Driver ODBC 17 dari repo Microsoft -- sama dengan driver yang disebut DATABASE_URL.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list -o /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 libgssapi-krb5-2 \
 && apt-get purge -y curl gnupg && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 3001
# Satu proses, banyak thread: rem login (login_guard) dan tiket unduhan
# (tiket_unduh) disimpan di memori proses. Multi-worker memecahnya per worker.
CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:3001", "--timeout", "120", "run:app"]
