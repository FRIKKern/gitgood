FROM docker.io/library/ubuntu@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ENV DEBIAN_FRONTEND=noninteractive ImageOS=ubuntu24
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git openssl openssh-client jq tar gzip python3 libicu74 docker.io sudo iproute2 procps build-essential unzip && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 1001 --user-group --groups docker --create-home --shell /bin/bash ci && printf 'ci ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/ci && chmod 0440 /etc/sudoers.d/ci
RUN mkdir -p /home/ci/runner && curl -fsSL --retry 2 https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-x64-2.338.0.tar.gz -o /tmp/runner.tar.gz && echo 'af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32  /tmp/runner.tar.gz' | sha256sum --check && tar -xzf /tmp/runner.tar.gz -C /home/ci/runner && rm /tmp/runner.tar.gz && chown -R ci:ci /home/ci/runner
USER ci
WORKDIR /home/ci/runner
