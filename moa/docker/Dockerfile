FROM python:3.12-slim
# stdlib 만 사용 — pip 설치 없음
COPY agent.py /agent.py
# 비루트 사용자로 실행(추가 방어)
RUN useradd -m -u 10001 moa
USER moa
ENTRYPOINT ["python", "/agent.py"]
