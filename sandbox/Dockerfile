FROM python:3.11-slim
RUN useradd -u 10001 -m runner
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER runner
WORKDIR /work
CMD ["python", "/work/main.py"]
