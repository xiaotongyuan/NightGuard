FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONPATH=src
ENV PORT=7860

EXPOSE 7860
CMD ["python", "-m", "nightguard.ui_server", "--llm", "fake"]
