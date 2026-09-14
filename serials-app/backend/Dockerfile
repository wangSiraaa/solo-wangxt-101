FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 启动：迁移 -> 幂等写入演示数据与更正场景 -> gunicorn
CMD ["sh", "-c", "python manage.py migrate && python manage.py seed_demo && python manage.py seed_corrections && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2"]
