FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/server
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./
# routers/team_icon.py가 기동 시 static/team_icons를 만들어 팀 로고 캐시를 쓴다 -
# appuser로 전환하기 전에 미리 만들어 소유권을 넘겨줘야 런타임에 mkdir 권한 오류가 안 난다.
RUN useradd --create-home appuser \
    && mkdir -p static/team_icons \
    && chown -R appuser:appuser /app/server
USER appuser
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
