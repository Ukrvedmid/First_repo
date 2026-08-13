#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="${APP_USER:-ultbear}"
REPO_DIR="${REPO_DIR:-/home/ultbear/job-agent}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-production}"
STATE_DIR="${STATE_DIR:-/var/lib/job-agent-autodeploy}"
LOCK_FILE="${LOCK_FILE:-/run/lock/job-agent-autodeploy.lock}"
ENV_FILE="${ENV_FILE:-${REPO_DIR}/.env}"
SERVICE_NAME="${SERVICE_NAME:-agent}"
HEALTH_WAIT_SECONDS="${HEALTH_WAIT_SECONDS:-25}"

mkdir -p "${STATE_DIR}" "$(dirname "${LOCK_FILE}")"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    exit 0
fi

log() {
    local message="$*"
    printf '[%s] %s\n' "$(date -Is)" "${message}"
    logger -t job-agent-autodeploy -- "${message}" 2>/dev/null || true
}

read_env_value() {
    local key="$1"
    local value=""
    if [[ -r "${ENV_FILE}" ]]; then
        value="$(awk -v wanted="${key}" '
            index($0, wanted "=") == 1 {
                sub(/^[^=]*=/, "")
                sub(/\r$/, "")
                print
                exit
            }
        ' "${ENV_FILE}")"
    fi
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    printf '%s' "${value}"
}

notify_telegram() {
    local text="$1"
    local token chat_id
    token="$(read_env_value TELEGRAM_BOT_TOKEN)"
    chat_id="$(read_env_value TELEGRAM_CHAT_ID)"

    if [[ -z "${token}" || -z "${chat_id}" ]]; then
        return 0
    fi

    curl -fsS --max-time 20 \
        -X POST "https://api.telegram.org/bot${token}/sendMessage" \
        --data-urlencode "chat_id=${chat_id}" \
        --data-urlencode "text=${text}" \
        --data-urlencode "disable_web_page_preview=true" \
        >/dev/null 2>&1 || true
}

git_as_app_user() {
    runuser -u "${APP_USER}" -- git -C "${REPO_DIR}" "$@"
}

container_is_running() {
    local container_id status
    container_id="$(docker compose -f "${REPO_DIR}/docker-compose.yml" \
        --project-directory "${REPO_DIR}" ps -q "${SERVICE_NAME}" 2>/dev/null || true)"
    [[ -n "${container_id}" ]] || return 1
    status="$(docker inspect -f '{{.State.Status}}' "${container_id}" 2>/dev/null || true)"
    [[ "${status}" == "running" ]]
}

container_is_healthy() {
    local container_id status restart_count fatal_line
    container_id="$(docker compose -f "${REPO_DIR}/docker-compose.yml" \
        --project-directory "${REPO_DIR}" ps -q "${SERVICE_NAME}")"
    if [[ -z "${container_id}" ]]; then
        log "Health check failed: no container ID for service ${SERVICE_NAME}."
        return 1
    fi

    sleep "${HEALTH_WAIT_SECONDS}"
    status="$(docker inspect -f '{{.State.Status}}' "${container_id}" 2>/dev/null || true)"
    restart_count="$(docker inspect -f '{{.RestartCount}}' "${container_id}" 2>/dev/null || echo 999)"

    if [[ "${status}" != "running" ]]; then
        log "Health check failed: container status is ${status:-unknown}."
        return 1
    fi
    if ! [[ "${restart_count}" =~ ^[0-9]+$ ]] || (( restart_count > 0 )); then
        log "Health check failed: container restart count is ${restart_count}."
        return 1
    fi

    fatal_line="$(docker compose -f "${REPO_DIR}/docker-compose.yml" \
        --project-directory "${REPO_DIR}" logs --since="${HEALTH_WAIT_SECONDS}s" \
        "${SERVICE_NAME}" 2>&1 \
        | grep -E 'Traceback|ImportError|ModuleNotFoundError|\[FATAL-SCAN\]' \
        | tail -n 1 || true)"
    if [[ -n "${fatal_line}" ]]; then
        log "Health check failed: ${fatal_line}"
        return 1
    fi

    return 0
}

rollback_release() {
    local previous_commit="$1"
    local failed_commit="$2"
    local failure_reason="$3"

    set +e
    printf '%s\n' "${failed_commit}" > "${STATE_DIR}/failed_commit"
    log "Deployment failed for ${failed_commit:0:12}: ${failure_reason}. Rolling back to ${previous_commit:0:12}."

    git_as_app_user checkout -B "${DEPLOY_BRANCH}" "${previous_commit}"
    local checkout_status=$?
    if (( checkout_status == 0 )); then
        docker compose -f "${REPO_DIR}/docker-compose.yml" \
            --project-directory "${REPO_DIR}" build
        local build_status=$?
        if (( build_status == 0 )); then
            docker compose -f "${REPO_DIR}/docker-compose.yml" \
                --project-directory "${REPO_DIR}" up -d \
                --remove-orphans --force-recreate
        fi
    fi

    notify_telegram "❌ Job Agent: обновление ${failed_commit:0:12} не прошло проверку. Выполнен откат на ${previous_commit:0:12}. Причина: ${failure_reason}."
    exit 1
}

if [[ ! -d "${REPO_DIR}/.git" ]]; then
    log "Repository not found: ${REPO_DIR}."
    exit 1
fi
if ! id "${APP_USER}" >/dev/null 2>&1; then
    log "Application user does not exist: ${APP_USER}."
    exit 1
fi
if [[ ! -f "${ENV_FILE}" ]]; then
    log "Environment file not found: ${ENV_FILE}. Deployment was not attempted."
    notify_telegram "⚠️ Job Agent: автодеплой остановлен — отсутствует ${ENV_FILE}."
    exit 1
fi

for command in git runuser docker curl flock; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        log "Required command is missing: ${command}."
        exit 1
    fi
done
if ! docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin is unavailable."
    exit 1
fi

# Executable bits are not part of the deployment contract because systemd runs
# this file through bash. Ignoring mode-only differences prevents chmod or mount
# semantics from creating a false dirty-worktree condition.
git_as_app_user config core.fileMode false

if ! git_as_app_user fetch --prune origin "${DEPLOY_BRANCH}"; then
    log "Could not fetch origin/${DEPLOY_BRANCH}."
    exit 1
fi

current_commit="$(git_as_app_user rev-parse HEAD)"
target_commit="$(git_as_app_user rev-parse "origin/${DEPLOY_BRANCH}")"
failed_commit="$(cat "${STATE_DIR}/failed_commit" 2>/dev/null || true)"
deployed_commit="$(cat "${STATE_DIR}/deployed_commit" 2>/dev/null || true)"

if [[ "${current_commit}" == "${target_commit}" \
      && "${deployed_commit}" == "${target_commit}" ]] \
      && container_is_running; then
    exit 0
fi
if [[ -n "${failed_commit}" && "${target_commit}" == "${failed_commit}" ]]; then
    log "Skipping previously failed release ${target_commit:0:12}; waiting for a newer production commit."
    exit 0
fi

if ! git_as_app_user diff --quiet || ! git_as_app_user diff --cached --quiet; then
    dirty_files="$(git_as_app_user status --short | head -n 20 | tr '\n' '; ')"
    log "Tracked local changes detected. Automatic deployment was blocked to avoid data loss. Files: ${dirty_files:-unknown}."
    notify_telegram "⚠️ Job Agent: автодеплой заблокирован — в репозитории есть локальные изменения отслеживаемых файлов: ${dirty_files:-не определены}."
    exit 1
fi

previous_commit="${current_commit}"
commit_subject="$(git_as_app_user log -1 --pretty=%s "${target_commit}" | head -c 180)"
log "Deploying ${target_commit:0:12}: ${commit_subject}"

if ! git_as_app_user checkout -B "${DEPLOY_BRANCH}" "${target_commit}"; then
    rollback_release "${previous_commit}" "${target_commit}" "git checkout failed"
fi

if ! docker compose -f "${REPO_DIR}/docker-compose.yml" \
    --project-directory "${REPO_DIR}" config -q; then
    rollback_release "${previous_commit}" "${target_commit}" "docker compose configuration is invalid"
fi

if ! docker compose -f "${REPO_DIR}/docker-compose.yml" \
    --project-directory "${REPO_DIR}" build --pull; then
    rollback_release "${previous_commit}" "${target_commit}" "container image build failed"
fi

if ! docker compose -f "${REPO_DIR}/docker-compose.yml" \
    --project-directory "${REPO_DIR}" run --rm --no-deps \
    --entrypoint python "${SERVICE_NAME}" \
    -c 'import app.main; import app.matcher; import app.location; import app.notify'; then
    rollback_release "${previous_commit}" "${target_commit}" "application import smoke test failed"
fi

if ! docker compose -f "${REPO_DIR}/docker-compose.yml" \
    --project-directory "${REPO_DIR}" up -d \
    --remove-orphans --force-recreate; then
    rollback_release "${previous_commit}" "${target_commit}" "container start failed"
fi

if ! container_is_healthy; then
    rollback_release "${previous_commit}" "${target_commit}" "container health check failed"
fi

rm -f "${STATE_DIR}/failed_commit"
printf '%s\n' "${target_commit}" > "${STATE_DIR}/deployed_commit"
log "Deployment successful: ${target_commit:0:12}."
notify_telegram "✅ Job Agent автоматически обновлён до ${target_commit:0:12}. ${commit_subject}"

# Remove only old, unused images. Named volumes and the vacancy database are not touched.
docker image prune -f --filter 'until=168h' >/dev/null 2>&1 || true
