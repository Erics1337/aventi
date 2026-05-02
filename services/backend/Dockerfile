# Lambda container image for the Aventi backend.
#
# One image serves three Lambdas (api, worker, scheduler). Terraform overrides
# the handler per-function via image_config.command:
#   - aws_lambda_function.api       -> aventi_backend.api.lambda_handler.handler
#   - aws_lambda_function.worker    -> aventi_backend.worker.lambda_handler.handler (default CMD)
#   - aws_lambda_function.scheduler -> aventi_backend.worker.scheduler.handler

FROM public.ecr.aws/lambda/python:3.13

# Install uv (fast, deterministic dependency resolution).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR ${LAMBDA_TASK_ROOT}

# Dependency layer: copied first so Docker caches it across code-only changes.
# README.md is listed because pyproject.toml's `readme = "README.md"` makes
# hatchling look for it during export-generated builds.
COPY pyproject.toml uv.lock README.md ./

# Install runtime deps directly into ${LAMBDA_TASK_ROOT} (Lambda's import root).
# `uv export` includes a self-referential `-e .` line for the aventi-backend
# package; strip it so uv doesn't try to build the project inside the image —
# we copy src/ below instead (smaller + faster).
RUN uv export \
      --no-hashes \
      --no-dev \
      --frozen \
      --no-emit-project \
      --format requirements-txt \
      --output-file /tmp/requirements.txt \
 && uv pip install \
      --system \
      --target ${LAMBDA_TASK_ROOT} \
      --requirement /tmp/requirements.txt \
 && rm /tmp/requirements.txt

# Copy application source. Keep this last so deps don't reinstall on code edits.
COPY src/aventi_backend ${LAMBDA_TASK_ROOT}/aventi_backend

# Default handler is the SQS-triggered worker; api + scheduler override via
# Terraform's image_config.command.
CMD ["aventi_backend.worker.lambda_handler.handler"]
