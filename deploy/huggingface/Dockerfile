# Muhr backend (registry + three sellers) as one Hugging Face Docker Space.
#
# A Space exposes a single port, so scripts/run_space.py starts the sellers on localhost and
# the registry on $PORT. The image pulls the code from the public repository at build time;
# change REPO_URL / REPO_REF (Space settings > Variables, as build args) to use a fork or branch.

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Spaces run containers as user 1000.
RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    DATABASE_URL=sqlite:////home/user/data/muhr.db

WORKDIR /home/user/app

ARG REPO_URL=https://github.com/ibrahimalee/muhr.git
ARG REPO_REF=main
RUN git clone --depth 1 --branch "${REPO_REF}" "${REPO_URL}" . \
    && mkdir -p /home/user/data

# The registry's requirements cover the sellers too (same pinned versions).
RUN pip install --no-cache-dir -r registry/requirements.txt

EXPOSE 7860
CMD ["python", "scripts/run_space.py"]
