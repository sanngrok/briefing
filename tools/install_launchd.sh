#!/bin/bash
# 토스증권 동기화 자동 실행 등록/해제 (macOS launchd)
#
#   ./tools/install_launchd.sh            등록 (기본 .venv 의 python 사용)
#   ./tools/install_launchd.sh /path/python   다른 파이썬으로 등록
#   ./tools/install_launchd.sh --uninstall    해제
#
# 등록하면 평일 16:30 에 portfolio.json 이 갱신된다. 대시보드 반영은 여전히
# 브라우저에서 '가져오기' 를 눌러야 한다(보유 정보는 localStorage 에만 있다).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.briefing.tosssync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "해제했습니다: $PLIST"
  exit 0
fi

PYTHON="${1:-$REPO/.venv/bin/python}"
[ -x "$PYTHON" ] || { echo "파이썬을 찾을 수 없습니다: $PYTHON" >&2; exit 1; }
"$PYTHON" -c "import requests" 2>/dev/null || {
  echo "이 파이썬에 requests 가 없습니다. pip install -r tools/requirements.txt" >&2; exit 1; }
[ -f "$REPO/.env" ] || { echo ".env 가 없습니다 (TOSS_CLIENT_ID/SECRET 필요)" >&2; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents" "$REPO/tools/logs"
sed -e "s|__REPO__|$REPO|g" -e "s|__PYTHON__|$PYTHON|g" \
    "$REPO/tools/launchd/$LABEL.plist" > "$PLIST"

# 이미 등록돼 있으면 내리고 다시 올린다(설정 변경 반영)
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

echo "등록했습니다: $PLIST"
echo "  파이썬 : $PYTHON"
echo "  작업   : 평일 16:30  ->  $REPO/portfolio.json"
echo "  로그   : $REPO/tools/logs/tosssync.log"
echo
echo "지금 한 번 돌려보려면:"
echo "  launchctl kickstart -k gui/$(id -u)/$LABEL && sleep 5 && tail -20 $REPO/tools/logs/tosssync.log"
