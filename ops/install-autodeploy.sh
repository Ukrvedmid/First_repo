#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
    echo "Запусти установку через sudo: sudo bash /home/ultbear/job-agent/ops/install-autodeploy.sh" >&2
    exit 1
fi

APP_USER="${APP_USER:-${SUDO_USER:-ultbear}}"
if [[ "${APP_USER}" == "root" ]]; then
    APP_USER="ultbear"
fi
REPO_DIR="${REPO_DIR:-/home/${APP_USER}/job-agent}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-production}"
STATE_DIR="/var/lib/job-agent-autodeploy"

if ! id "${APP_USER}" >/dev/null 2>&1; then
    echo "Пользователь ${APP_USER} не найден." >&2
    exit 1
fi
if [[ ! -d "${REPO_DIR}/.git" ]]; then
    echo "Репозиторий не найден: ${REPO_DIR}" >&2
    exit 1
fi
if [[ ! -f "${REPO_DIR}/.env" ]]; then
    echo "Файл ${REPO_DIR}/.env не найден. Telegram-секреты должны сохраниться до установки." >&2
    exit 1
fi

for command in git runuser docker curl flock systemctl install; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "Не найдена обязательная команда: ${command}" >&2
        exit 1
    fi
done
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin не найден." >&2
    exit 1
fi

chown -R "${APP_USER}:${APP_USER}" "${REPO_DIR}"
chmod 600 "${REPO_DIR}/.env"
install -d -m 0755 "${STATE_DIR}"

runuser -u "${APP_USER}" -- bash -c \
    'grep -qxF ".env" "$1/.git/info/exclude" 2>/dev/null || echo ".env" >> "$1/.git/info/exclude"' \
    _ "${REPO_DIR}"

runuser -u "${APP_USER}" -- git -C "${REPO_DIR}" fetch --prune origin "${DEPLOY_BRANCH}"
runuser -u "${APP_USER}" -- git -C "${REPO_DIR}" checkout -B "${DEPLOY_BRANCH}" "origin/${DEPLOY_BRANCH}"

install -m 0644 "${REPO_DIR}/ops/job-agent-autodeploy.service" \
    /etc/systemd/system/job-agent-autodeploy.service
install -m 0644 "${REPO_DIR}/ops/job-agent-autodeploy.timer" \
    /etc/systemd/system/job-agent-autodeploy.timer
chmod 0755 "${REPO_DIR}/ops/job-agent-autodeploy.sh"

systemctl daemon-reload
systemctl enable --now job-agent-autodeploy.timer
systemctl start job-agent-autodeploy.service

echo
echo "===== AUTODEPLOY INSTALLED ====="
systemctl --no-pager --full status job-agent-autodeploy.timer | sed -n '1,12p'
echo
echo "Следующая проверка:"
systemctl list-timers job-agent-autodeploy.timer --no-pager

echo
echo "Проверка сервиса:"
systemctl --no-pager --full status job-agent-autodeploy.service | sed -n '1,18p' || true
