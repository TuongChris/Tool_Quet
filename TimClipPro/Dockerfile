# Chi dung khi ban muon dong goi he thong (v2) - v1 chay truc tiep bang ChayTool.bat
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# audfprint di kem trong image; neu thieu thi tai luc build
RUN test -f audfprint-master/audfprint.py || \
    (curl -L -o /tmp/a.zip https://github.com/dpwe/audfprint/archive/refs/heads/master.zip \
     && python -c "import zipfile;zipfile.ZipFile('/tmp/a.zip').extractall('.')")

EXPOSE 8501
HEALTHCHECK CMD curl -f http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", \
     "--server.port=8501", "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
