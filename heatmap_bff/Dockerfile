FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Build aggregates if data exists during build
RUN if [ -f "./data/tracks.csv" ]; then \
        echo "Building H3 aggregates during Docker build..."; \
        PYTHONPATH=/app python -m heatmap_bff.scripts.build_precomputed \
            --input ./data/tracks.csv \
            --out ./outputs/h3_aggregates.csv \
            --res 6 7 8 \
            --k 20; \
    else \
        echo "No data file found, skipping aggregates build"; \
        mkdir -p ./outputs; \
    fi

# Precomputed aggregates expected at this path
ENV PRECOMPUTED_AGG=./outputs/h3_aggregates.csv

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
