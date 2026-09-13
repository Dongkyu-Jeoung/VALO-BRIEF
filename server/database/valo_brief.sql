-- =====================================================================
-- VALO-BRIEF 데이터베이스 스키마 — 최종 통합본
-- 엔진: MySQL 8.0+ / InnoDB / utf8mb4
--
-- 이 파일 하나로 DB 생성부터 전체 테이블·참조 데이터까지 한 번에 구성됩니다.

-- 테이블 생성 순서는 FK 의존관계를 따릅니다:
--   ref_maps/ref_agents/ref_weapons/ref_player_cards/ref_player_titles → teams
--   → riot_accounts → matches → match_player_stats
--   → team_stats_summary/player_stats_summary → predictions → insights
--
-- 2026-09-08 재정리 (7차 재검토 - 상세 근거는 server/우리팀_기능_구현_가이드.md):
--   - team_members 테이블 제거. 팀 대표자를 개인 계정 단위로 지정하기가 실무적으로
--     어려워서(누가 대표인지 정하기 애매함), 팀 인증을 team_name/team_tag 기준으로만
--     하기로 최종 결정했습니다 - 그러면 "이 팀의 대표 Riot 계정이 누구인지"를 매핑해둘
--     이유가 없어집니다.
--   - teams: tier_id/season/conference 컬럼 제거(같은 이유), team_image 컬럼 추가
--     (Henrik customization.image 팀 로고 URL), team_id를 AUTO_INCREMENT INT에서
--     VARCHAR(64)로 변경. division/ranking_points는 유지.
--     ※ premier_team_id는 별도 컬럼으로 안 남기고 team_id 자체로 흡수했습니다 -
--     team_id 값 자체가 Henrik 프리미어 팀의 실제 id입니다(회원가입 시
--     services/henrik_api.get_premier_team(team_name, team_tag) 조회 결과의 id를
--     그대로 씀 - routers/auth.py 참고). 즉 team_name/team_tag가 실제 존재하는
--     프리미어 팀이어야만 가입이 됩니다.
--   - team_id 타입 변경에 맞춰 이를 참조하던 모든 FK 컬럼(team_stats_summary.team_id,
--     matches.team_a_id/team_b_id/winner_team_id, match_player_stats.team_id,
--     predictions.team_a_id/team_b_id, insights.team_id/opponent_team_id)도 전부
--     VARCHAR(64)로 함께 변경했습니다.
--
-- 2026-09-08 프론트 소스 대조 (우리팀_기능_구현_가이드.md 4-2/4-3번) 반영:
--   - matches: rounds_won_a/rounds_won_b 추가 (TeamMatchRow.jsx의 match.roundScore 대응).
--   - match_player_stats: is_mvp 추가 (TeamMatchRow.jsx의 match.mvp 대응).
--   - teams: verified/verified_at 추가 - 팀 대표 개인 계정이 없어져서 riot_accounts에
--     있던 인증 상태를 팀 단위(team_name/team_tag)로 옮겼습니다.
--   - riot_accounts: verification_status/verified_at 제거 (위 이유로 더 이상 팀 단위
--     계정에서 쓸 근거가 없음).
-- 이미 RDS에 생성되어 있는 DB에는 이 파일 맨 아래 "마이그레이션" 섹션의 SQL을
-- 실행하세요 (team_id 타입이 바뀌면서 여러 테이블의 FK를 순서대로 내렸다 올리는
-- 다단계 마이그레이션입니다 - 실행 전 꼭 검토하세요).
--
-- 운영 RDS 직접 대조(SHOW CREATE TABLE 전체 테이블) 후 정정:
--   - matches/match_player_stats/predictions/insights/team_stats_summary의 teams
--     참조 FK(fk_matches_team_a/b/winner, fk_mps_team, fk_predictions_team_a/b,
--     fk_insights_team/opponent, fk_tss_team)는 이 파일의 마이그레이션 7)/10)번이
--     의도했던 것과 달리 운영 RDS에 실제로는 하나도 존재하지 않았다(전부 인덱스만
--     있고 FK 제약은 없음). 특히 insights.opponent_team_id는 비가입 상대팀을 가리키는
--     행이 실제로 28건 있어(승부예측/AI 리포트가 비가입 팀도 검색 대상으로 삼기 때문)
--     FK를 걸면 그 자체로 위반이다 - "FK 없음"이 최종 설계로 확정되었으므로 이 파일도
--     그에 맞춰 정정했다(해당 CREATE TABLE/마이그레이션 섹션의 2026-09-14 주석 참고).
--   - 그 외 컬럼 구성(테이블 12개: ref_maps/ref_agents/ref_weapons/ref_player_cards/
--     ref_player_titles/teams/riot_accounts/player_rolling_cache/team_engagement_cache/
--     matches/match_player_stats/team_stats_summary/player_stats_summary/predictions/
--     insights)은 운영 RDS와 이 파일이 이미 정확히 일치함을 확인했다.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. 데이터베이스 생성
-- ---------------------------------------------------------------------
DROP DATABASE IF EXISTS valobrief;
CREATE DATABASE valobrief
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE valobrief;

-- 클라이언트 접속 인코딩을 명시적으로 고정 (한글 등 멀티바이트 문자 깨짐/이중인코딩 방지)
SET NAMES utf8mb4;

-- ---------------------------------------------------------------------
-- 1. REF_MAPS / REF_AGENTS / REF_WEAPONS  (요원·무기·맵 GUID 참조 테이블)
-- ---------------------------------------------------------------------
-- 데이터 출처 및 검증 방법:
--   맵     : valorant-api.com/v1/maps 실제 응답을 직접 fetch, mapUrl 필드를
--            matchdetails의 mapId와 1:1 대조 (전체 26개, 100% 직접 검증)
--   요원   : valorant-api.com/v1/agents?isPlayableCharacter=true 응답 직접 fetch
--            (전체 29명, 100% 직접 검증)
--   무기   : 18개 전부 개별 교차검증. verified_source 컬럼 참고
--            - api_direct : valorant-api.com UUID 직접 조회 (Odin, Ares)
--            - valofessor : valofessor.gg(실 데이터 기반 3자 사이트) weaponId 대조
--            - datasci    : 공개 Riot ContentItemDTO 원본 덤프 대조
--   ⚠️ 검증 중 발견된 정정: 기존에 통용되던 "표준 UUID" 중 아래 5개는 실제로
--      서로 뒤바뀌어 있었음(a03b24d3=Vandal→실제 Operator, ee8e8d15=Operator→실제 Phantom,
--      9c82e19d=Phantom→실제 Vandal, 4ade7faa=Bulldog→실제 Guardian,
--      462080d1=Judge→실제 Spectre). 이 파일 값은 전부 검증을 마친 최종 확정값입니다.
--
-- synced_at: 외부 API(valorant-api.com) 마지막 동기화 시각. 이 데이터는 영구
-- 고정이 아니라(신규 요원/맵/무기가 계속 추가됨), 주기적 재동기화가 필요합니다.
-- ---------------------------------------------------------------------
CREATE TABLE ref_maps (
    uuid            VARCHAR(64)     NOT NULL COMMENT 'valorant-api.com map uuid',
    display_name    VARCHAR(30)     NOT NULL COMMENT '영문 기준명',
    name_ko         VARCHAR(30)     NULL COMMENT '한글 표시명 - Henrik /v1/content localizedNames.ko-KR로 패치 시 동기화 (seed_reference_tables.py)',
    map_url         VARCHAR(100)    NOT NULL COMMENT 'matchdetails.mapId 와 동일 포맷 (조인 키)',
    site_layout     VARCHAR(10)     NULL COMMENT '예: A/B, A/B/C',
    is_competitive  BOOLEAN         NOT NULL DEFAULT FALSE,
    synced_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    COMMENT '외부 API 마지막 동기화 시각',
    PRIMARY KEY (uuid),
    UNIQUE KEY uq_ref_maps_url (map_url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='맵 GUID 참조 테이블';

INSERT INTO ref_maps (uuid, display_name, name_ko, map_url, site_layout, is_competitive) VALUES
('7eaecc1b-4337-bbf6-6ab9-04b8f06b3319','Ascent','어센트','/Game/Maps/Ascent/Ascent','A/B',1),
('d960549e-485c-e861-8d71-aa9d1aed12a2','Split','스플릿','/Game/Maps/Bonsai/Bonsai','A/B',1),
('b529448b-4d60-346e-e89e-00a4c527a405','Fracture','프랙처','/Game/Maps/Canyon/Canyon','A/B',1),
('2c9d57ec-4431-9c5e-2939-8f9ef6dd5cba','Bind','바인드','/Game/Maps/Duality/Duality','A/B',1),
('2fb9a4fd-47b8-4e7d-a969-74b4046ebd53','Breeze','브리즈','/Game/Maps/Foxtrot/Foxtrot','A/B',1),
('224b0a95-48b9-f703-1bd8-67aca101a61f','Abyss','어비스','/Game/Maps/Infinity/Infinity','A/B',1),
('2fe4ed3a-450a-948b-6d6b-e89a78e680a9','Lotus','로터스','/Game/Maps/Jam/Jam','A/B/C',1),
('92584fbe-486a-b1b2-9faa-39b0f486b498','Sunset','선셋','/Game/Maps/Juliett/Juliett','A/B',1),
('fd267378-4d1d-484f-ff52-77821ed10dc2','Pearl','펄','/Game/Maps/Pitt/Pitt','A/B',1),
('756da597-416b-c0f2-f47b-afbdf28670bc','Summit','서밋','/Game/Maps/Plummet/Plummet','A/B',1),
('e2ad5c54-4114-a870-9641-8ea21279579a','Icebox','아이스박스','/Game/Maps/Port/Port','A/B',1),
('1c18ab1f-420d-0d8b-71d0-77ad3c439115','Corrode','코로드','/Game/Maps/Rook/Rook','A/B',1),
('2bee0dc9-4ffe-519b-1cbd-7fbe763a6047','Haven','헤이븐','/Game/Maps/Triad/Triad','A/B/C',1),
('a9009649-421f-d5d5-f80c-0cbe02c125bb','Skirmish A','난투 A','/Game/Maps/Duel/Duel_1/Skirmish_A',NULL,0),
('a38a3f9a-4042-844c-8970-a3ac2f7ce93d','Skirmish B','난투 B','/Game/Maps/Duel/Duel_2/Skirmish_B',NULL,0),
('a264de0f-4a04-9c78-c97a-a6b192ce6e86','Skirmish C','난투 C','/Game/Maps/Duel/Duel_3/Skirmish_C',NULL,0),
('1c7555fc-4bc6-3b98-9674-789d47ef6c50','Skirmish D','난투 D','/Game/Maps/Duel/Duel_Platform/Skirmish_D',NULL,0),
('4490f1d6-4818-bf5f-9b3a-9c9a8dbb52ed','Skirmish E','난투 E','/Game/Maps/Duel/Duel_Heady/Skirmish_E',NULL,0),
('690b3ed2-4dff-945b-8223-6da834e30d24','District','디스트릭트','/Game/Maps/HURM/HURM_Alley/HURM_Alley',NULL,0),
('12452a9d-48c3-0b02-e7eb-0381c3520404','Kasbah','카즈바','/Game/Maps/HURM/HURM_Bowl/HURM_Bowl',NULL,0),
('2c09d728-42d5-30d8-43dc-96a05cc7ee9d','Drift','드리프트','/Game/Maps/HURM/HURM_Helix/HURM_Helix',NULL,0),
('d6336a5a-428f-c591-98db-c8a291159134','Glitch','글리치','/Game/Maps/HURM/HURM_HighTide/HURM_HighTide',NULL,0),
('de28aa9b-4cbe-1003-320e-6cb3ec309557','Piazza','피아자','/Game/Maps/HURM/HURM_Yard/HURM_Yard',NULL,0),
('1f10dab3-4294-3827-fa35-c2aa00213cf3','Basic Training',NULL,'/Game/Maps/NPEV2/NPEV2',NULL,0),
('ee613ee9-28b7-4beb-9666-08db13bb2244','The Range',NULL,'/Game/Maps/Poveglia/Range',NULL,0),
('5914d1e0-40c4-cfdd-6b88-eba06347686c','The Range (V2)',NULL,'/Game/Maps/PovegliaV2/RangeV2',NULL,0);

CREATE TABLE ref_agents (
    uuid            VARCHAR(64)     NOT NULL COMMENT 'valorant-api.com agent uuid = matchdetails.characterId',
    display_name    VARCHAR(30)     NOT NULL COMMENT '영문 기준명',
    name_ko         VARCHAR(30)     NULL COMMENT '한글 표시명 - Henrik /v1/content localizedNames.ko-KR로 패치 시 동기화 (seed_reference_tables.py)',
    role_type       ENUM('Duelist','Initiator','Controller','Sentinel') NOT NULL,
    synced_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    COMMENT '외부 API 마지막 동기화 시각 - 신규 요원 출시 시 갱신 필요',
    PRIMARY KEY (uuid),
    UNIQUE KEY uq_ref_agents_name (display_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='요원 GUID 참조 테이블';

INSERT INTO ref_agents (uuid, display_name, name_ko, role_type) VALUES
('e370fa57-4757-3604-3648-499e1f642d3f','Gekko','게코','Initiator'),
('dade69b4-4f5a-8528-247b-219e5a1facd6','Fade','페이드','Initiator'),
('5f8d3a7f-467b-97f3-062c-13acf203c006','Breach','브리치','Initiator'),
('cc8b64c8-4b25-4ff9-6e7f-37b4da43d235','Deadlock','데드락','Sentinel'),
('b444168c-4e35-8076-db47-ef9bf368f384','Tejo','테호','Initiator'),
('f94c3b30-42be-e959-889c-5aa313dba261','Raze','레이즈','Duelist'),
('22697a3d-45bf-8dd7-4fec-84a9e28c69d7','Chamber','체임버','Sentinel'),
('601dbbe7-43ce-be57-2a40-4abd24953621','KAYO','케이오','Initiator'),
('6f2a04ca-43e0-be17-7f36-b3908627744d','Skye','스카이','Initiator'),
('117ed9e3-49f3-6512-3ccf-0cada7e3823b','Cypher','사이퍼','Sentinel'),
('320b2a48-4d9b-a075-30f1-1f93a9b638fa','Sova','소바','Initiator'),
('7c8a4701-4de6-9355-b254-e09bc2a34b72','Miks','믹스','Controller'),
('1e58de9c-4950-5125-93e9-a0aee9f98746','Killjoy','킬조이','Sentinel'),
('95b78ed7-4637-86d9-7e41-71ba8c293152','Harbor','하버','Controller'),
('efba5359-4016-a1e5-7626-b1ae76895940','Vyse','바이스','Sentinel'),
('707eab51-4836-f488-046a-cda6bf494859','Viper','바이퍼','Controller'),
('eb93336a-449b-9c1b-0a54-a891f7921d69','Phoenix','피닉스','Duelist'),
('92eeef5d-43b5-1d4a-8d03-b3927a09034b','Veto','비토','Sentinel'),
('41fb69c1-4189-7b37-f117-bcaf1e96f1bf','Astra','아스트라','Controller'),
('9f0d8ba9-4140-b941-57d3-a7ad57c6b417','Brimstone','브림스톤','Controller'),
('0e38b510-41a8-5780-5e8f-568b2a4f2d6c','Iso','아이소','Duelist'),
('1dbf2edd-4729-0984-3115-daa5eed44993','Clove','클로브','Controller'),
('bb2a4828-46eb-8cd1-e765-15848195d751','Neon','네온','Duelist'),
('7f94d92c-4234-0a36-9646-3a87eb8b5c89','Yoru','요루','Duelist'),
('df1cb487-4902-002e-5c17-d28e83e78588','Waylay','웨이레이','Duelist'),
('569fdd95-4d10-43ab-ca70-79becc718b46','Sage','세이지','Sentinel'),
('a3bfb853-43b2-7238-a4f1-ad90e9e46bcc','Reyna','레이나','Duelist'),
('8e253930-4c05-31dd-1b6c-968525494517','Omen','오멘','Controller'),
('add6443a-41bd-e414-f6ad-e58d267f4e95','Jett','제트','Duelist');

CREATE TABLE ref_weapons (
    uuid            VARCHAR(64)     NOT NULL COMMENT 'valorant-api.com weapon uuid = finishingDamage.damageItem',
    display_name    VARCHAR(30)     NOT NULL COMMENT '영문 기준명',
    name_ko         VARCHAR(30)     NULL COMMENT '한글 표시명 - Henrik /v1/content localizedNames.ko-KR로 패치 시 동기화 (seed_reference_tables.py)',
    category        ENUM('Sidearm','SMG','Shotgun','Rifle','Sniper','Heavy') NOT NULL,
    base_cost       INT             NOT NULL,
    verified_source ENUM('api_direct','valofessor','datasci') NOT NULL
        COMMENT 'api_direct=valorant-api.com 실시간 직접조회, valofessor=실데이터 기반 3자 사이트 대조, datasci=공개 ContentItemDTO 덤프 대조',
    synced_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    COMMENT '외부 API 마지막 동기화 시각 - 신규 무기 출시 시 갱신 필요',
    PRIMARY KEY (uuid),
    UNIQUE KEY uq_ref_weapons_name (display_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='무기 GUID 참조 테이블';

INSERT INTO ref_weapons (uuid, display_name, name_ko, category, base_cost, verified_source) VALUES
('63e6c2b6-4a8e-869c-3d4c-e38355226584','Odin','오딘','Heavy',3200,'api_direct'),
('55d8a0f4-4274-ca67-fe2c-06ab45efdf58','Ares','아레스','Heavy',1600,'api_direct'),
('29a0cfab-485b-f5d5-779a-b59f85e204a8','Classic','클래식','Sidearm',0,'valofessor'),
('42da8ccc-40d5-affc-beec-15aa47b42eda','Shorty','쇼티','Sidearm',150,'valofessor'),
('44d4e95c-4157-0037-81b2-17841bf2e8e3','Frenzy','프렌지','Sidearm',450,'valofessor'),
('1baa85b4-4c70-1284-64bb-6481dfc3bb4e','Ghost','고스트','Sidearm',500,'valofessor'),
('e336c6b8-418d-9340-d77f-7a9e4cfe0702','Sheriff','셰리프','Sidearm',800,'valofessor'),
('f7e1b454-4ad4-1063-ec0a-159e56b58941','Stinger','스팅어','SMG',1000,'valofessor'),
('462080d1-4035-2937-7c09-27aa2a5c27a7','Spectre','스펙터','SMG',1600,'datasci'),
('910be174-449b-c412-ab22-d0873436b21b','Bucky','버키','Shotgun',850,'valofessor'),
('ec845bf4-4f79-ddda-a3da-0db3774b2794','Judge','저지','Shotgun',1850,'valofessor'),
('ae3de142-4d85-2547-dd26-4e90bed35cf7','Bulldog','불독','Rifle',2050,'valofessor'),
('4ade7faa-4cf1-8376-95ef-39884480959b','Guardian','가디언','Rifle',2250,'datasci'),
('ee8e8d15-496b-07ac-e5f6-8fae5d4c7b1a','Phantom','팬텀','Rifle',2900,'valofessor'),
('9c82e19d-4575-0200-1a81-3eacf00cf872','Vandal','밴달','Rifle',2900,'valofessor'),
('c4883e50-4494-202c-3ec3-6b8a9284f00b','Marshal','마샬','Sniper',1100,'datasci'),
('5f0aaf7a-4289-3998-d5ff-eb9a5cf7ef5c','Outlaw','아웃로','Sniper',2400,'valofessor'),
('a03b24d3-4319-996d-0f8c-94bbfba1dfc7','Operator','오퍼레이터','Sniper',4700,'datasci');

-- ---------------------------------------------------------------------
-- 1-1. REF_PLAYER_CARDS / REF_PLAYER_TITLES  (프로필 아바타/칭호 참조 테이블)
--
-- ref_agents/ref_maps/ref_weapons와 달리 개수가 많아(카드 982개, 칭호 415개, 계속 늘어남)
-- 전체를 미리 시드하지 않는다. Henrik account API가 puuid마다 card/title uuid를 주면,
-- 처음 보는 uuid만 valorant-api.com(GET /v1/playercards|playertitles/{uuid}?language=ko-KR)
-- 에서 그때그때 조회해 이 테이블에 캐싱해두는 cache-aside 방식이다
-- (services/cosmetics.py 참고, riot_accounts 캐싱과 같은 패턴).
-- ---------------------------------------------------------------------
CREATE TABLE ref_player_cards (
    uuid            VARCHAR(64)     NOT NULL COMMENT 'valorant-api.com playercard uuid = Henrik account.card',
    name_ko         VARCHAR(100)    NULL COMMENT 'valorant-api.com displayName (language=ko-KR)',
    display_icon    VARCHAR(255)    NULL COMMENT '프로필 아바타용 소형 아이콘 URL',
    synced_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='플레이어 카드(아바타) 참조 테이블 - 최초 조회 시 캐싱';

CREATE TABLE ref_player_titles (
    uuid            VARCHAR(64)     NOT NULL COMMENT 'valorant-api.com playertitle uuid = Henrik account.title',
    title_ko        VARCHAR(100)    NULL COMMENT 'valorant-api.com titleText (language=ko-KR)',
    synced_at       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='플레이어 칭호 참조 테이블(텍스트만, 이미지 없음) - 최초 조회 시 캐싱';

-- ---------------------------------------------------------------------
-- 2. TEAMS  (팀 단위 계정 - 회원가입/로그인/팀 프로필 겸용)
--
-- 2026-09-08 재정리 (7차 재검토 - server/우리팀_기능_구현_가이드.md 참고):
--   - tier_id/season/conference 컬럼 제거. 팀 인증을 대표 개인 계정이 아니라
--     team_name/team_tag 기준으로 하기로 하면서(대표자를 지정하기 어렵다는 실무 이유)
--     별도로 안 들고 있어도 되는 값들이 됨.
--   - division/ranking_points는 유지 (13번 재검토와 달리 이번엔 유지로 확정 - 팀 프로필
--     헤더에 캐싱해서 보여줄 값으로 남겨둠).
--   - team_image 신규 추가 - Henrik 프리미어 API의 customization.image(팀 로고) 원격
--     URL을 그대로 저장 (front ProfileHeader.jsx의 avatarUrl prop과 동일 개념,
--     services/team_profile.py의 ratingIconUrl과 같은 소스).
--   - team_id: AUTO_INCREMENT INT → VARCHAR(64)로 변경하면서 premier_team_id 컬럼을
--     따로 두지 않고 team_id 자체가 그 값을 갖도록 흡수했다. 즉 회원가입 시
--     services/henrik_api.get_premier_team(team_name, team_tag)로 실제 프리미어 팀을
--     조회해서 그 응답의 id를 그대로 team_id로 쓴다(routers/auth.py의 signup() 참고) -
--     team_name/team_tag가 실제 존재하는 프리미어 팀이 아니면 애초에 team_id를 정할 수
--     없어 가입 자체가 실패한다. 이 변경 때문에 teams.team_id를 참조하는 다른
--     테이블들의 FK 컬럼도 전부 VARCHAR(64)로 같이 바뀐다(team_stats_summary.team_id,
--     matches.team_a_id/team_b_id/winner_team_id, match_player_stats.team_id,
--     predictions.team_a_id/team_b_id, insights.team_id/opponent_team_id).
-- ---------------------------------------------------------------------
CREATE TABLE teams (
    team_id             VARCHAR(64)     NOT NULL COMMENT 'Henrik 프리미어 팀 API(get_premier_team) 응답의 id를 그대로 사용 (회원가입 시 team_name/team_tag로 조회)',
    email               VARCHAR(255)    NOT NULL,
    login_id            VARCHAR(50)     NOT NULL,
    password_hash       VARCHAR(255)    NOT NULL,
    privacy_agreed      BOOLEAN         NOT NULL DEFAULT FALSE,
    team_name           VARCHAR(50)     NOT NULL,
    team_tag            VARCHAR(10)     NOT NULL,
    team_image          VARCHAR(255)    NULL COMMENT '팀 로고 - Henrik 프리미어 API customization.image 원격 URL',
    verified            BOOLEAN         NOT NULL DEFAULT FALSE
                                        COMMENT 'team_name/team_tag가 실제 Henrik 프리미어 팀으로 확인됐는지 (팀 단위 인증 - 우리팀_기능_구현_가이드.md 4-3번)',
    verified_at         DATETIME        NULL,
    division             VARCHAR(20)    NULL,
    ranking_points      INT             NOT NULL DEFAULT 0,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id),
    UNIQUE KEY uq_teams_login_id (login_id),
    UNIQUE KEY uq_teams_email (email),
    UNIQUE KEY uq_teams_name_tag (team_name, team_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀 단위 계정 (개인 로그인 없음, op.gg 스타일)';

-- ---------------------------------------------------------------------
-- 3. RIOT_ACCOUNTS  (로스터 개인 Riot 계정 - 서비스 로그인과 무관)
-- ---------------------------------------------------------------------
CREATE TABLE riot_accounts (
    puuid               VARCHAR(64)     NOT NULL COMMENT 'Riot PUUID (고정키)',
    riot_name           VARCHAR(50)     NOT NULL,
    riot_tag            VARCHAR(10)     NOT NULL,
    region              VARCHAR(10)     NOT NULL,
    platform            VARCHAR(10)     NOT NULL DEFAULT 'pc',
    account_level       INT             NULL COMMENT 'Henrik account API account_level',
    title               VARCHAR(100)    NULL COMMENT '칭호 한글 텍스트 (ref_player_titles로 변환된 값, uuid 아님)',
    avatar_url           VARCHAR(255)    NULL COMMENT '프로필 카드 아바타 이미지 URL (ref_player_cards로 변환된 값)',
    current_rank        VARCHAR(30)     NULL COMMENT 'Henrik mmr API current.tier.name',
    current_rr          INT             NULL COMMENT 'Henrik mmr API current.rr',
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid),
    UNIQUE KEY uq_riot_accounts_name_tag (riot_name, riot_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Riot 개인 계정 (로스터 구성원)';

-- ---------------------------------------------------------------------
-- 3-1. PLAYER_ROLLING_CACHE  (선수별 Rolling Feature 캐시)
--
-- 2026-09-08 신규: 승부예측(ml/predictor.py, ml/rolling.py)이 매번 Henrik에서 다시
-- 계산하던 "최근 5경기 평균"(acs/kd/kast/headshot_pct/winrate)을 puuid 단위로
-- 캐싱한다. riot_accounts(계정 정보, 사실상 무기한 유효)와 달리 이 값은 선수가 새
-- 경기를 하면 바뀌므로 애플리케이션 레벨 TTL(ml/rolling.py ROLLING_CACHE_TTL)로
-- 일정 시간 뒤엔 무효로 취급한다 - 그래서 riot_accounts에 대한 FK를 걸지 않았다
-- (predict 파이프라인이 riot_accounts에 그 puuid를 먼저 upsert해둔다는 보장이 없음).
-- ---------------------------------------------------------------------
CREATE TABLE player_rolling_cache (
    puuid                   VARCHAR(64)     NOT NULL COMMENT 'Riot PUUID (고정키)',
    agent                   VARCHAR(30)     NULL COMMENT '최근 경기 중 가장 최근 매치의 요원',
    recent_acs              FLOAT           NOT NULL,
    recent_kd               FLOAT           NOT NULL,
    recent_kast             FLOAT           NOT NULL,
    recent_headshot_pct     FLOAT           NOT NULL,
    recent_winrate          FLOAT           NOT NULL,
    computed_at             DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='선수별 Rolling Feature(최근 N경기 평균) 캐시 - TTL은 애플리케이션에서 관리';

-- ---------------------------------------------------------------------
-- 3-2. TEAM_ENGAGEMENT_CACHE  (팀×매치당 교전 매치업 Rolling Feature 로그)
--
-- 2026-09-08 신규, 같은 날 재설계: 처음엔 팀당 한 행(덮어쓰기)짜리 캐시였지만,
-- matches/match_player_stats에 원본을 저장하지 않기로 하면서(server/승부예측_성능_
-- 분석.md 11번) 이 표가 "지금 이 팀의 최근 폼" 캐시와 "모델 재학습용 원본" 두 역할을
-- 겸하도록 팀×매치당 한 행(append-only 로그)으로 바꿨다. services/match_history.py가
-- 매치 상세를 받는 즉시(write-through) 그 매치 하나만의 트레이드 성공률/듀얼리스트
-- ACS를 계산해서 upsert한다 - Team에 FK는 걸지 않음(미가입 팀은 애초에 캐싱 대상이
-- 아님, matches.team_a_id/team_b_id도 FK 없던 기존 관례와 동일).
-- ---------------------------------------------------------------------
CREATE TABLE team_engagement_cache (
    team_id                 VARCHAR(64)     NOT NULL COMMENT 'teams.team_id (Henrik 프리미어 팀 id)',
    match_id                VARCHAR(64)     NOT NULL COMMENT '이 팀이 이 매치에서 기록한 값',
    opponent_team_id        VARCHAR(64)     NULL     COMMENT '상대도 가입 팀이면 그 team_id (학습 데이터 페어링용)',
    game_start               DATETIME        NULL     COMMENT '정렬/최근 N경기 선정 기준',
    trade_rate              FLOAT           NULL     COMMENT '이 매치에서의 트레이드 성공률(%) - 계산 불가 시 NULL',
    duelist_acs             FLOAT           NULL     COMMENT '이 매치에서의 듀얼리스트 로스터 평균 ACS - 계산 불가 시 NULL',
    win                     BOOLEAN         NULL     COMMENT '이 매치의 실제 승패(Henrik teams.{side}.has_won) - 최근 승률 피처(diff_win_rate)와 메타 모델 라벨(label_win)의 원천',
    computed_at             DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, match_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀x매치당 교전 매치업(트레이드 성공률/듀얼리스트 ACS/승패) 값 - 캐시 + 학습 데이터 겸용';

-- ---------------------------------------------------------------------
-- 4. MATCHES  (매치 메타데이터 캐시)
--    ※ map_name(varchar) 대신 map_uuid(FK → ref_maps)로 구성
--
-- 2026-09-07: 한 번 DROP 후보(코드에서 안 쓴다는 이유)였다가 되돌림 - "우리팀 로스터
-- 멤버 스탯"을 보여주는 화면(우리팀 분석, 3초 상대분석 등)마다 매번 Henrik 매치 상세
-- (v2/match, 건당 ~1.3MB)를 실시간으로 다시 불러오면 성능 부담이 크다는 지적을 받아
-- 되살렸다. Henrik이 이미 원본을 갖고 있으니 여기서는 "다시 파싱할 필요 없이 로컬에서
-- 바로 집계"하기 위한 캐시로 쓴다 - match_player_stats/team_stats_summary/
-- player_stats_summary를 채우는 원본 소스 (server/우리팀_기능_구현_가이드.md 참고).
-- 아직 이 테이블에 쓰는 서비스 코드는 없음 - 우리팀 로스터 스탯 캐싱 기능을 구현할 때
-- Henrik에서 가져온 매치 상세를 여기 저장하는 로직과 함께 만들면 됨.
-- ---------------------------------------------------------------------
CREATE TABLE matches (
    match_id            VARCHAR(64)     NOT NULL COMMENT 'Riot match id (UUID)',
    map_uuid            VARCHAR(64)     NULL COMMENT 'REF_MAPS.uuid 참조',
    mode                VARCHAR(30)     NULL,
    game_start          DATETIME        NULL,
    team_a_id           VARCHAR(64)     NULL,
    team_b_id           VARCHAR(64)     NULL,
    winner_team_id      VARCHAR(64)     NULL,
    rounds_won_a        INT             NULL COMMENT 'team_a_id 팀이 획득한 라운드 수',
    rounds_won_b        INT             NULL COMMENT 'team_b_id 팀이 획득한 라운드 수',
    round_detail_json   JSON            NULL COMMENT '라운드/킬/데미지 원본 (필요시에만 파싱)',
    api_source          VARCHAR(30)     NULL COMMENT '예: premier_history, v4_matches',
    collected_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_id),
    KEY idx_matches_map (map_uuid),
    KEY idx_matches_team_a (team_a_id),
    KEY idx_matches_team_b (team_b_id),
    KEY idx_matches_winner (winner_team_id),
    KEY idx_matches_game_start (game_start),
    -- 2026-09-14 운영 RDS 대조 후 정정: team_a_id/team_b_id/winner_team_id는 FK를
    -- 걸지 않는다(과거엔 걸려 있었으나 실제 운영 RDS에는 한 번도 반영된 적이 없었음 -
    -- 아래 "마이그레이션" 섹션 7번 참고). 매치의 상대팀은 이 서비스에 가입하지 않은
    -- 임의의 프리미어 팀일 수 있어(team_engagement_cache 주석의 "기존 관례"와 동일
    -- 이유), 강한 FK를 걸면 그런 매치를 저장할 때마다 실패한다. 조회 성능은 아래
    -- 일반 인덱스(idx_matches_team_a/b/winner)로 확보한다.
    CONSTRAINT fk_matches_map
        FOREIGN KEY (map_uuid) REFERENCES ref_maps (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='매치 메타데이터 캐시';

-- ---------------------------------------------------------------------
-- 5. MATCH_PLAYER_STATS  (매치별 선수 집계 스탯 캐시)
--    ※ agent(varchar) → agent_uuid(FK → ref_agents)
--    ※ most_used_weapon(varchar) → most_used_weapon_uuid(FK → ref_weapons)
--
-- matches와 같은 이유로 유지 - 팀 로스터 멤버별 스탯(무기/역할/킬·데스 등)을 매번
-- Henrik 매치 상세에서 다시 파싱하지 않고 이미 파싱해둔 값을 바로 읽기 위한 캐시.
-- ---------------------------------------------------------------------
CREATE TABLE match_player_stats (
    stat_id                 INT             NOT NULL AUTO_INCREMENT,
    match_id                VARCHAR(64)     NOT NULL,
    puuid                   VARCHAR(64)     NOT NULL,
    team_id                 VARCHAR(64)     NULL,
    is_mvp                  BOOLEAN         NOT NULL DEFAULT FALSE COMMENT '그 매치에서 team_id 로스터 내 MVP였는지',
    agent_uuid              VARCHAR(64)     NULL COMMENT 'REF_AGENTS.uuid 참조',
    role_type               VARCHAR(20)     NULL COMMENT '타격대/척후대/감시자/전략가',
    started_at              DATETIME        NULL COMMENT 'Henrik 프리미어 히스토리 API(GET /valorant/v1/premier/{team}/{tag}/history) league_matches[].started_at',
    acs                     INT             NULL,
    kills                   INT             NULL,
    deaths                  INT             NULL,
    assists                 INT             NULL,
    headshot_pct            FLOAT           NULL,
    kast                    FLOAT           NULL,
    adr                     INT             NULL,
    first_bloods            INT             NULL,
    first_deaths            INT             NULL,
    most_used_weapon_uuid   VARCHAR(64)     NULL COMMENT 'REF_WEAPONS.uuid 참조',
    detail_json             JSON            NULL COMMENT '부위별 타격, 무기별 세부, 클러치 플래그 등',
    PRIMARY KEY (stat_id),
    UNIQUE KEY uq_match_player (match_id, puuid),
    KEY idx_mps_puuid (puuid),
    KEY idx_mps_team (team_id),
    KEY idx_mps_agent (agent_uuid),
    KEY idx_mps_weapon (most_used_weapon_uuid),
    CONSTRAINT fk_mps_match
        FOREIGN KEY (match_id) REFERENCES matches (match_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_mps_puuid
        FOREIGN KEY (puuid) REFERENCES riot_accounts (puuid)
        ON DELETE CASCADE ON UPDATE CASCADE,
    -- team_id는 matches.team_a_id/team_b_id와 같은 이유로 FK 없음(위 4번 주석 참고) -
    -- idx_mps_team 인덱스만 유지.
    CONSTRAINT fk_mps_agent
        FOREIGN KEY (agent_uuid) REFERENCES ref_agents (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_mps_weapon
        FOREIGN KEY (most_used_weapon_uuid) REFERENCES ref_weapons (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='매치별 선수 집계 스탯 캐시';

-- ---------------------------------------------------------------------
-- 6. TEAM_STATS_SUMMARY  (팀 단위 집계: 맵/사이드/조합/라운드페이즈/교전 등)
--
-- 2026-09-07: 한 번 DROP 후보로 분류했다가 되돌림 - "3초 상대분석 리포트"(QuickAnalysisModal),
-- "상대팀 vs 우리팀 분석"(MatchPredictionPage AnalysisTab), "우리팀 맞춤 전략 제안"
-- (MyTeamAnalysisPage/MatchPredictionPage AiReportTab)이 아직 백엔드 미구현이라 실제
-- 코드에서는 안 쓰지만, front/src/mocks/prediction.mock.js의 analysis.roundInfo/
-- mapInfoByMap/engagementInfo, front/src/mocks/myTeam.mock.js의 myTeamAnalysisMock이
-- 이 테이블의 stat_type(map_side/agent/composition/round_phase/engagement) 구조와
-- 그대로 대응된다. "3초" 안에 응답해야 하는 화면이라 매번 Henrik 매치 상세를 다시 불러
-- 실시간 집계하기엔 느려서(팀당 매치 1건 ~1.3MB, team_profile.py 주석 참고), 이 집계
-- 결과를 미리 계산해 캐싱해두는 용도로 필요하다고 판단해 유지한다. matches/
-- match_player_stats에 캐싱해둔 원본으로부터 이 집계를 계산한다.
-- ---------------------------------------------------------------------
CREATE TABLE team_stats_summary (
    summary_id          INT             NOT NULL AUTO_INCREMENT,
    team_id             VARCHAR(64)     NOT NULL,
    stat_type           ENUM('map_side','agent','composition','round_phase','engagement')
                                        NOT NULL,
    dimension_key       VARCHAR(100)    NOT NULL
        COMMENT 'stat_type=map_side/agent일 때 REF_MAPS.uuid 또는 REF_AGENTS.uuid를 값으로 사용 (폴리모픽이라 강한 FK 없음)',
    wins                INT             NOT NULL DEFAULT 0,
    losses              INT             NOT NULL DEFAULT 0,
    metrics_json        JSON            NULL COMMENT '유형별 상이한 세부 지표',
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (summary_id),
    UNIQUE KEY uq_team_stats (team_id, stat_type, dimension_key)
    -- 2026-09-14 운영 RDS 대조 후 정정: fk_tss_team(teams FK)은 마이그레이션 7번에서
    -- 재생성하려 했으나 실제 운영 RDS에는 반영된 적이 없다. 이 컬럼은 항상 가입 팀만
    -- 가리키므로(비가입 상대팀 케이스 없음) 나중에 FK를 걸어도 안전하지만, 우선
    -- 실제 운영 상태와 이 문서를 일치시킨다.
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀 단위 집계 통계';

-- ---------------------------------------------------------------------
-- 7. PLAYER_STATS_SUMMARY  (개인 단위 집계: 무기/히트박스/클러치/역할매치업/교전 등)
--
-- team_stats_summary와 같은 이유로 유지 - front/src/mocks/myTeam.mock.js의
-- myTeamPlayerDetailMock.aim(hitzones/weapons/clutch), .engagement가 이 테이블의
-- stat_type(weapon/hitbox/clutch/role_matchup/engagement)과 1:1로 대응된다
-- ("우리팀 맞춤 전략 제안"의 선수별 피드백 카드용 데이터). matches/match_player_stats에
-- 캐싱해둔 원본으로부터 이 집계를 계산한다.
-- ---------------------------------------------------------------------
CREATE TABLE player_stats_summary (
    summary_id          INT             NOT NULL AUTO_INCREMENT,
    puuid               VARCHAR(64)     NOT NULL,
    stat_type           ENUM('weapon','hitbox','clutch','role_matchup','engagement','round_phase')
                                        NOT NULL
        COMMENT 'round_phase는 2026-09-10 선수 상세 페이지(①라운드 정보) 캐싱용으로 추가 -
                 team_stats_summary.stat_type의 round_phase/map_side를 선수 개인 단위로 합친 것',
    dimension_key       VARCHAR(100)    NOT NULL
        COMMENT 'stat_type=weapon일 때 REF_WEAPONS.uuid, round_phase일 때 REF_MAPS.uuid 또는
                 "overall"을 값으로 사용 (폴리모픽이라 강한 FK 없음). 예: Head, 1v1',
    metrics_json        JSON            NULL,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (summary_id),
    UNIQUE KEY uq_player_stats (puuid, stat_type, dimension_key),
    CONSTRAINT fk_pss_puuid
        FOREIGN KEY (puuid) REFERENCES riot_accounts (puuid)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='개인 단위 집계 통계';

-- ---------------------------------------------------------------------
-- 8. PREDICTIONS  (승부 예측 결과 - Layer1 모델 산출값)
--    routers/predict.py(GET /api/predict/{team_name}/{team_tag})가 예측할 때마다 저장한다.
--    ※ map_name(varchar) → map_uuid(FK → ref_maps)
--
-- 2026-09-07 재검토: team_b_id(상대팀)를 NOT NULL FK로 두면 "이 서비스에 가입 안 한
-- 임의의 프리미어 팀"을 상대로 예측할 때(원래 이 기능의 정상적인 주 사용 케이스 - 팀
-- 검색과 동일한 패턴) FK 위반으로 저장 자체가 실패한다. team_b_id를 nullable로 바꾸고
-- (가입 팀이면 채워짐, 아니면 NULL) opponent_team_name/opponent_team_tag를 추가해
-- 가입 여부와 무관하게 상대팀을 항상 식별할 수 있게 했다.
-- ---------------------------------------------------------------------
CREATE TABLE predictions (
    prediction_id       INT             NOT NULL AUTO_INCREMENT,
    team_a_id           VARCHAR(64)     NOT NULL,
    team_b_id           VARCHAR(64)     NULL COMMENT '상대팀이 가입 계정일 때만 채워짐(teams.team_id)',
    opponent_team_name  VARCHAR(50)     NOT NULL COMMENT '상대팀 가입 여부와 무관하게 항상 채워짐',
    opponent_team_tag   VARCHAR(10)     NOT NULL,
    map_uuid             VARCHAR(64)    NULL COMMENT 'REF_MAPS.uuid 참조',
    predicted_winrate_a FLOAT           NOT NULL,
    predicted_winrate_b FLOAT           NOT NULL,
    model_version       VARCHAR(30)     NOT NULL,
    feature_snapshot_json JSON          NULL,
    actual_result       VARCHAR(10)     NULL COMMENT 'A_WIN / B_WIN / NULL(미확정)',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (prediction_id),
    KEY idx_predictions_team_a (team_a_id),
    KEY idx_predictions_team_b (team_b_id),
    KEY idx_predictions_map (map_uuid),
    -- 2026-09-14 운영 RDS 대조 후 정정: team_a_id/team_b_id도 FK 없음(4번 matches
    -- 주석과 동일 사유 - 마이그레이션 10번에서 team_b_id용 FK를 재생성하려 했으나
    -- 실제 운영 RDS에는 반영된 적이 없다). idx_predictions_team_a/b 인덱스만 유지.
    CONSTRAINT fk_predictions_map
        FOREIGN KEY (map_uuid) REFERENCES ref_maps (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='승부 예측 모델(Layer1) 결과';

-- ---------------------------------------------------------------------
-- 9. INSIGHTS  (AI 리포트 - 팀/개인 서술형 결과, Layer2)
--    2026-09-11: services/ai_report.py가 "우리팀 분석 > AI 리포트" 탭용으로 실제 사용
--    시작(AI_리포트_개발_설계.md 참고). 리포트 하나 = 여러 행(문장 단위):
--      target_type='team', opponent_team_id=NULL  → insight_type
--        'summary'(팀 개요 1행) / 'strength'(3행) / 'weakness'(3행) / 'strategy'(전술 제안 1행)
--      target_type='player', target_puuid=로스터 puuid → insight_type
--        'strength'(1행) / 'weakness'(1행)
--    upsert 키가 없어 재생성 시 해당 팀의 opponent_team_id IS NULL 행 전체를 지우고
--    새로 넣는 방식으로 "교체"한다. agent_comment/personal_feedback은 아직 미사용.
-- ---------------------------------------------------------------------
CREATE TABLE insights (
    insight_id          INT             NOT NULL AUTO_INCREMENT,
    team_id             VARCHAR(64)     NOT NULL,
    opponent_team_id    VARCHAR(64)     NULL COMMENT '매치업 리포트일 때만 사용',
    target_type         ENUM('team','player')  NOT NULL DEFAULT 'team',
    target_puuid        VARCHAR(64)     NULL COMMENT 'target_type=player일 때만 사용',
    insight_type        VARCHAR(30)     NULL COMMENT 'weakness, strategy, personal_feedback, agent_comment',
    content              TEXT           NOT NULL,
    generated_at         DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (insight_id),
    KEY idx_insights_team (team_id),
    KEY idx_insights_opponent (opponent_team_id),
    KEY idx_insights_target_puuid (target_puuid),
    -- 2026-09-14 운영 RDS 대조 후 정정: team_id/opponent_team_id는 FK 없음. 특히
    -- opponent_team_id는 services/opponent_ai_report.py가 Henrik에서 조회한 상대팀의
    -- id를 가입 여부와 무관하게 그대로 저장하므로(승부예측/AI 리포트는 비가입 팀도
    -- 검색 대상) teams에 없는 값이 정상적으로 존재한다 - 실측 결과 운영 RDS에 28건
    -- 존재(2026-09-14 기준). FK를 걸면 이 정상 케이스마다 저장이 실패한다.
    CONSTRAINT fk_insights_target_puuid
        FOREIGN KEY (target_puuid) REFERENCES riot_accounts (puuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AI 리포트(Layer2) - 팀/개인 서술형 결과';

-- =====================================================================
-- 끝
-- =====================================================================


-- #######################################################################
-- 마이그레이션 (이미 생성되어 있는 RDS DB에 적용)
--
-- 위 CREATE TABLE 문들은 "새 DB를 처음부터 만들 때" 기준 최종 스키마입니다.
-- 이미 예전 스키마로 생성되어 데이터가 들어있는 RDS에는 파일 맨 위 DROP DATABASE부터
-- 다시 실행하면 안 되고, 아래 ALTER/DROP 문만 한 번 실행해서 같은 상태로 맞추면 됩니다.
-- #######################################################################

SET FOREIGN_KEY_CHECKS = 0;

-- 1) 팀 대표자를 개인 계정 단위로 지정하기 어렵다는 실무 이유로, 팀 인증을
--    team_name/team_tag 기준으로만 하기로 하면서 team_members(로스터/대표자 매핑)를
--    완전히 제거합니다.
DROP TABLE IF EXISTS team_members;

-- 2) rank_snapshots 제거 - 랭크 추이 저장하는 코드/화면이 없고, Henrik mmr-history
--    (by_season)가 이미 Act별 최종 티어 이력을 제공해서 대체할 필요가 없습니다.
DROP TABLE IF EXISTS rank_snapshots;

-- 3) teams.team_id를 참조하는 모든 FK를 먼저 제거합니다 - 이후 team_id 컬럼 타입을
--    INT(AUTO_INCREMENT) -> VARCHAR(64)로 바꾸려면 이걸 참조하는 컬럼들의 FK가 먼저
--    없어져야 합니다.
ALTER TABLE team_stats_summary DROP FOREIGN KEY fk_tss_team;
ALTER TABLE matches
    DROP FOREIGN KEY fk_matches_team_a,
    DROP FOREIGN KEY fk_matches_team_b,
    DROP FOREIGN KEY fk_matches_winner;
ALTER TABLE match_player_stats DROP FOREIGN KEY fk_mps_team;
ALTER TABLE predictions
    DROP FOREIGN KEY fk_predictions_team_a,
    DROP FOREIGN KEY fk_predictions_team_b;
ALTER TABLE insights
    DROP FOREIGN KEY fk_insights_team,
    DROP FOREIGN KEY fk_insights_opponent;

-- 4) teams: premier_team_id/tier_id/season/conference 컬럼 제거(팀 인증을
--    team_name/team_tag 기준으로만 하기로 하면서 외부 프리미어 팀 ID를 별도로 안
--    들고 있어도 됨 - division/ranking_points는 유지), team_id를 AUTO_INCREMENT
--    INT에서 애플리케이션이 직접 채우는 VARCHAR(64)로 변경. premier_team_id/tier_id/
--    season/conference는 현재 운영 RDS에서 팀 4개 전부 NULL인 것을 확인했으므로
--    안전합니다. (team_image 컬럼 추가는 위 CREATE TABLE 섹션에 이미 반영되어 있어
--    여기서는 생략 - 2026-09-14 정리)
ALTER TABLE teams
    DROP FOREIGN KEY fk_teams_tier,
    DROP COLUMN premier_team_id,
    DROP COLUMN tier_id,
    DROP COLUMN season,
    DROP COLUMN conference,
    MODIFY COLUMN team_id VARCHAR(64) NOT NULL COMMENT 'Henrik 프리미어 팀 API(get_premier_team) 응답의 id를 그대로 사용 (회원가입 시 team_name/team_tag로 조회)';
-- team_id는 INT -> VARCHAR 전환이라 기존 값(예: 3)은 MySQL이 문자열('3')로 그대로
-- 보존합니다 - 기존 4개 팀 행이 사라지지 않습니다. 다만 이후 신규 가입 팀부터는
-- routers/auth.py의 signup()이 henrik_api.get_premier_team()으로 조회한 실제
-- premier team id를 services/auth.py의 create_team()에 넘겨서 team_id로 씁니다
-- (AUTO_INCREMENT가 더 이상 동작하지 않음 - team_name/team_tag가 실제 프리미어 팀이
-- 아니면 가입 자체가 실패합니다).

-- 5) teams.tier_id가 참조하던 premier_tiers도 함께 제거 (참조하는 컬럼이 없어짐)
DROP TABLE IF EXISTS premier_tiers;

-- 6) teams.team_id를 참조하던 컬럼들도 같은 타입(VARCHAR(64))으로 맞춰 변경합니다.
ALTER TABLE team_stats_summary MODIFY COLUMN team_id VARCHAR(64) NOT NULL;
ALTER TABLE matches
    MODIFY COLUMN team_a_id VARCHAR(64) NULL,
    MODIFY COLUMN team_b_id VARCHAR(64) NULL,
    MODIFY COLUMN winner_team_id VARCHAR(64) NULL;
ALTER TABLE match_player_stats MODIFY COLUMN team_id VARCHAR(64) NULL;
ALTER TABLE predictions
    MODIFY COLUMN team_a_id VARCHAR(64) NOT NULL,
    MODIFY COLUMN team_b_id VARCHAR(64) NOT NULL;
ALTER TABLE insights
    MODIFY COLUMN team_id VARCHAR(64) NOT NULL,
    MODIFY COLUMN opponent_team_id VARCHAR(64) NULL;

-- 7) [2026-09-14 정정] 원래는 3)에서 내렸던 FK들을 새 타입 기준으로 다시 걸 계획이었지만,
--    운영 RDS를 직접 대조한 결과 아래 ADD CONSTRAINT 문들은 실제로 한 번도 실행된 적이
--    없었다(운영 RDS의 team_stats_summary/matches/match_player_stats/predictions/insights
--    어디에도 teams를 참조하는 FK가 존재하지 않음, 2026-09-14 SHOW CREATE TABLE로 확인).
--    게다가 insights.opponent_team_id는 승부예측/AI 리포트가 비가입 상대팀도 검색 대상으로
--    삼기 때문에(services/opponent_ai_report.py) teams에 없는 값이 실제로 28건 존재해
--    fk_insights_opponent를 걸면 그 자체로 실패한다. 즉 "FK 없음"이 사고가 아니라 이
--    스키마의 실제 최종 상태다 - 이 파일 위쪽 CREATE TABLE 섹션도 이에 맞춰 정정했다.
--    아래 문장들은 실행하지 말 것(기록 보존 목적으로만 남겨둠).
-- ALTER TABLE team_stats_summary
--     ADD CONSTRAINT fk_tss_team FOREIGN KEY (team_id) REFERENCES teams (team_id)
--         ON DELETE CASCADE ON UPDATE CASCADE;
-- ALTER TABLE matches
--     ADD CONSTRAINT fk_matches_team_a FOREIGN KEY (team_a_id) REFERENCES teams (team_id)
--         ON DELETE SET NULL ON UPDATE CASCADE,
--     ADD CONSTRAINT fk_matches_team_b FOREIGN KEY (team_b_id) REFERENCES teams (team_id)
--         ON DELETE SET NULL ON UPDATE CASCADE,
--     ADD CONSTRAINT fk_matches_winner FOREIGN KEY (winner_team_id) REFERENCES teams (team_id)
--         ON DELETE SET NULL ON UPDATE CASCADE;
-- ALTER TABLE match_player_stats
--     ADD CONSTRAINT fk_mps_team FOREIGN KEY (team_id) REFERENCES teams (team_id)
--         ON DELETE SET NULL ON UPDATE CASCADE;
-- ALTER TABLE predictions
--     ADD CONSTRAINT fk_predictions_team_a FOREIGN KEY (team_a_id) REFERENCES teams (team_id)
--         ON DELETE CASCADE ON UPDATE CASCADE,
--     ADD CONSTRAINT fk_predictions_team_b FOREIGN KEY (team_b_id) REFERENCES teams (team_id)
--         ON DELETE CASCADE ON UPDATE CASCADE;
-- ALTER TABLE insights
--     ADD CONSTRAINT fk_insights_team FOREIGN KEY (team_id) REFERENCES teams (team_id)
--         ON DELETE CASCADE ON UPDATE CASCADE,
--     ADD CONSTRAINT fk_insights_opponent FOREIGN KEY (opponent_team_id) REFERENCES teams (team_id)
--         ON DELETE SET NULL ON UPDATE CASCADE;

SET FOREIGN_KEY_CHECKS = 1;

-- 8) riot_accounts.verification_status/verified_at은 원래 "팀 대표 계정" 인증용이었는데
--    team_members가 없어지면서 그 근거가 사라졌습니다. 팀 인증은 team_name/team_tag를
--    Henrik 프리미어 팀 API로 조회하는 방식(teams.verified/verified_at)으로 옮깁니다
--    (우리팀_기능_구현_가이드.md 4-3번 참고). (teams.verified/verified_at 추가는 위
--    CREATE TABLE 섹션에 이미 반영되어 있어 여기서는 생략 - 2026-09-14 정리)
ALTER TABLE riot_accounts
    DROP COLUMN verification_status,
    DROP COLUMN verified_at;

-- 9) 프론트 TeamMatchRow.jsx가 라운드 스코어(match.roundScore)와 매치별 MVP
--    (match.mvp)를 표시하는데 대응하는 컬럼이 없었습니다 (우리팀_기능_구현_가이드.md
--    4-2번 참고). matches.rounds_won_a/b, match_player_stats.is_mvp 추가는 위
--    CREATE TABLE 섹션에 이미 반영되어 있어 여기서는 생략(추가할 ALTER 없음) -

-- 10) predictions.team_b_id(상대팀)를 NOT NULL FK로 두면, 이 서비스에 가입 안 한 임의의
--     프리미어 팀을 상대로 예측할 때(원래 이 기능의 정상적인 주 사용 케이스 - 팀 검색과
--     동일한 패턴) FK 위반으로 저장 자체가 실패합니다. team_b_id를 nullable로 바꿉니다
--     (가입 팀이면 채워짐, 아니면 NULL - opponent_team_name/opponent_team_tag가 가입
--     여부와 무관하게 상대팀을 항상 식별하며, 이 두 컬럼 추가는 위 CREATE TABLE
--     섹션에 이미 반영되어 있어 여기서는 생략 - 2026-09-14 정리).
ALTER TABLE predictions
    MODIFY COLUMN team_b_id VARCHAR(64) NULL COMMENT '상대팀이 가입 계정일 때만 채워짐(teams.team_id)';

-- 11) match_player_stats.side(Attack/Defense 등 - 실제로는 services/match_history.py가
--     red/blue 색상으로 채우고 있었음) 제거. 하프타임마다 공/수가 바뀌어서 매치당 값
--     1개로는 의미가 없는 컬럼이었고, side를 읽던 유일한 소비처(ml/engagement_training.py)도
--     이제 match_player_stats.team_id로 로스터를 가르도록 바뀌었다(services/match_sync.py/
--     match_history.py 모듈 docstring 참고). (대체로 추가된 started_at 컬럼은 위 CREATE
--     TABLE 섹션에 이미 반영되어 있어 여기서는 생략 - 2026-09-14 정리)
ALTER TABLE match_player_stats
    DROP COLUMN side;

-- 11)~13) player_rolling_cache 최초 생성, team_engagement_cache
--     최초 생성(팀당 1행 구버전), team_engagement_cache 재설계(팀×매치당 1행 신버전)
--     세 단계가 원래 여기 각각 CREATE TABLE로 남아있었는데, 두 테이블 모두 위 3-1/3-2번
--     섹션에 이미 최종 형태(win 컬럼까지 포함)로 정의돼 있어 중복이라 제거했다. 운영
--     RDS도 이미 최종 형태로 존재한다(2026-09-14 SHOW CREATE TABLE로 확인). 재설계
--     배경(팀당 1행 → 팀×매치당 1행으로 바꾼 이유)은 3-2번 섹션 주석 참고.

-- 14) 개인 분석 > 선수 상세 페이지(①라운드 정보 - 맵별 공격/수비/피스톨/Eco
--     K·D·ACS)를 player_stats_summary에 캐싱하기로 했는데, stat_type ENUM에 대응하는
--     값이 없었다(team_stats_summary는 round_phase/map_side가 있지만 player 쪽엔 없음).
--     선수 개인 단위로는 맵별/전체 구분을 dimension_key 하나로 합쳐도 되므로 round_phase
--     하나만 추가한다(services/my_team_player_detail.py 참고).
ALTER TABLE player_stats_summary
    MODIFY COLUMN stat_type ENUM('weapon','hitbox','clutch','role_matchup','engagement','round_phase') NOT NULL;

-- 15) team_engagement_cache에 win 컬럼 추가 - 이 매치의 실제 승패(Henrik
--     teams.{side}.has_won)를 그대로 저장한다. diff_win_rate(팀×매치 로그의 win으로 만든
--     "최근 승률 차이")가 실제 승패와의 상관계수 0.493으로 diff_trade_rate(0.276)보다도
--     강한 신호였다(1286건 기준 실측) - ml/engagement_training.py 참고. (win 컬럼 추가는
--     위 CREATE TABLE 섹션에 이미 반영되어 있어 여기서는 생략 - 2026-09-14 정리. 운영
--     RDS에 이미 이 컬럼이 존재하며, 과거 행은 win이 NULL로 남고 write-through가 다시
--     될 때 채워진다)

-- 원래 이 자리에 있던 "참고: insights, ref_weapons, team_stats_summary,
-- player_stats_summary는 현재 코드에서 아직 안 쓰지만... predictions는 routers/predict.py가...
-- 실제로 저장하기 시작했습니다" 문단은 코드 대조 결과 더 이상 사실이 아니어서 정정합니다:
--   - insights, team_stats_summary, player_stats_summary는 "아직 미사용 스캐폴딩"이
--     아니라 이미 실제로 읽고/쓰는 서비스가 있습니다 - team_stats_summary는
--     services/my_team_analysis.py, player_stats_summary는 services/my_team_
--     player_detail.py가 각각 "캐시 조회 → 없으면 matches/match_player_stats 원본으로
--     계산 → 결과를 다시 캐싱"하는 write-through 패턴으로 쓰고 있고, insights는
--     services/ai_report.py("우리팀 분석" 리포트)와 services/opponent_ai_report.py
--     ("승부예측" 상대팀 리포트) 둘 다 실제로 읽기/삭제/쓰기에 씁니다.
--   - 반대로 predictions는 이 문단의 설명과 달리 실제로는 저장되지 않습니다 -
--     services/predict_service.py::save_prediction() 함수 자체는 있지만 이 함수를
--     호출하는 곳이 코드 전체에 하나도 없습니다(routers/predict.py 포함). 즉 모델/
--     서비스 코드만 있고 실제로는 연결이 안 된 상태입니다.
--   - matches/match_player_stats는 이 문단 설명대로 services/match_history.py·
--     services/match_sync.py가 실제로 씁니다(정정 사항 없음).
--   - ref_weapons는 ORM 모델 없이 raw SQL로만 조회됩니다(services/my_team_player_
--     detail.py, services/match_sync.py) - agent/map 참조 테이블과 같은 방식.