"""
services/ai_report.py 프롬프트를 수정하는 동안, 브라우저 새로고침 → 캐시 삭제 →
페이지 렌더링까지 기다리지 않고 Claude 응답만 터미널에서 바로 확인하기 위한
개발용 스크립트. build_my_team_ai_report와 달리 insights 테이블을 읽거나 쓰지
않는다 - 프롬프트 반복 실험 중에는 캐시 판정/저장 과정 자체가 불필요한 지연이기
때문이다(9-11 4차 변경 관련 논의 참고).

사용법:
    python -m scripts.preview_ai_report <team_id>

team_id를 모르면 인자 없이 실행하면 teams 테이블에서 최근 매치가 있는 팀 상위
10개를 보여준다.
"""
import asyncio
import json
import sys

from database.connection import SessionLocal
from models.team import Team
from services import ai_report


def _print_stat_item(label: str, item: dict, indent: str = "  ") -> None:
    stat = item.get("stat") or "(없음)"
    title = item.get("title") or "(없음)"
    detail = item.get("detail") or []
    print(f"{indent}[{label}] stat={stat!r} title={title!r}")
    for i, line in enumerate(detail):
        print(f"{indent}  detail[{i}]={line!r}")


def _print_report(report: dict) -> None:
    print("\n=== intro ===")
    print(report["intro"])

    print("\n=== strengths ===")
    for i, s in enumerate(report["strengths"]):
        _print_stat_item(f"강점 {i + 1}", s)

    print("\n=== weaknesses ===")
    for i, w in enumerate(report["weaknesses"]):
        _print_stat_item(f"약점 {i + 1}", w)

    print("\n=== tactic ===")
    print(report["tactic"])

    print("\n=== playerFeedback ===")
    for fb in report["playerFeedback"]:
        print(f"\n- {fb['name']} ({fb['role']}, ACS {fb['acs']})")
        _print_stat_item("강점", fb["strength"], indent="    ")
        _print_stat_item("보완점", fb["weakness"], indent="    ")


async def preview(team_id: str, raw_json_only: bool = False) -> None:
    db = SessionLocal()
    try:
        team = db.query(Team).filter(Team.team_id == team_id).first()
        if not team:
            print(f"team_id={team_id} 를 찾을 수 없음")
            return

        context = ai_report._collect_team_context(db, team)
        roster, details = await ai_report._collect_roster_with_detail(db, team)
        system_prompt, user_prompt = ai_report._build_prompt(context, roster, details)

        print(f"로스터 {len(roster)}명, Claude 호출 중...")
        raw = ai_report._call_claude(system_prompt, user_prompt)
        if raw is None:
            print("ANTHROPIC_API_KEY 미설정 - 폴백 템플릿을 대신 출력합니다.")
            _print_report(ai_report._fallback_report(context, roster))
            return

        if raw_json_only:
            print(raw)
            return

        try:
            report = ai_report._parse_and_validate(raw, roster)
        except Exception as e:  # noqa: BLE001 - 검증 실패 시 원본 JSON을 보여줘야 디버깅 가능
            print(f"검증 실패: {e}\n\n--- 원본 응답 ---\n{raw}")
            return

        _print_report(report)
    finally:
        db.close()


def _list_recent_teams(db) -> None:
    from sqlalchemy import text

    rows = db.execute(
        text(
            "SELECT t.team_id, t.name FROM teams t "
            "JOIN matches m ON m.team_a_id = t.team_id OR m.team_b_id = t.team_id "
            "WHERE m.game_start IS NOT NULL "
            "GROUP BY t.team_id, t.name "
            "ORDER BY MAX(m.game_start) DESC LIMIT 10"
        )
    ).fetchall()
    if not rows:
        print("최근 매치가 있는 팀이 없음")
        return
    print("team_id를 인자로 주세요. 최근 매치가 있는 팀 목록:")
    for team_id, name in rows:
        print(f"  {team_id}  {name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    raw_only = "--raw" in args
    args = [a for a in args if a != "--raw"]

    if not args:
        _db = SessionLocal()
        try:
            _list_recent_teams(_db)
        finally:
            _db.close()
        sys.exit(0)

    asyncio.run(preview(args[0], raw_json_only=raw_only))