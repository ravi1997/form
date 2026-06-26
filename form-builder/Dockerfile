FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV FLASK_ENV=production
ENV MONGO_URI=mongodb://mongodb:27017/
ENV DB_NAME=form_builder_db

CMD ["python", "app.py"]
