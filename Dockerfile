FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY yohan_game.py .

CMD ["python", "yohan_game.py"]
