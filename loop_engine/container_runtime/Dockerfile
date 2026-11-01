FROM node:22-bookworm-slim AS node
FROM python:3.13-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/qa
COPY pyproject.toml ./
COPY requirements.lock ./
RUN python -c "import tomllib,subprocess; d=tomllib.load(open('pyproject.toml','rb'))['project']; subprocess.check_call(['python','-m','pip','install','--no-cache-dir',*d['dependencies'],*d['optional-dependencies']['dev']])" \
 && python -m pip install --no-cache-dir -r requirements.lock
WORKDIR /opt/node
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
# The configured Chromium project uses Playwright's default headless shell.
# Cache OS dependencies separately from the slow browser download.
RUN ./node_modules/.bin/playwright install-deps chromium
RUN ./node_modules/.bin/playwright install --only-shell chromium
RUN useradd --uid 1000 --no-create-home --home-dir /home --shell /usr/sbin/nologin loop-qa
ARG LOCUS_AUDIT_EPOCH
RUN test -n "$LOCUS_AUDIT_EPOCH" && python -m pip_audit && npm audit --audit-level=low
COPY supervisor.py /opt/supervisor.py
WORKDIR /work
ENTRYPOINT ["python", "/opt/supervisor.py"]
