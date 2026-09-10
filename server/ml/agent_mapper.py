# 모델은 Agent 의 이름을 사용했으므로 DB 에 존재하는 Agent 의 uuid -> name 변환 작업 필요
# DB 에 Agent 이름 추가하는게 더 편하지만 우선 해당 방법 사용

AGENT_UUID_TO_NAME = {
    # 실제 DB에 저장된 UUID를 여기에 대응
    # "uuid": "Jett",
    # "uuid": "Raze",
    # "uuid": "Omen",
}


def get_agent_name(agent_uuid):

    if agent_uuid is None:
        return "Unknown"

    return AGENT_UUID_TO_NAME.get(
        str(agent_uuid).lower(),
        "Unknown"
    )