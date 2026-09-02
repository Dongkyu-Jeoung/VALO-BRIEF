-- =====================================================================
-- VALO-BRIEF 데이터베이스 스키마 — 최종 통합본
-- 엔진: MySQL 8.0+ / InnoDB / utf8mb4
--
-- 이 파일 하나로 DB 생성부터 전체 테이블·참조 데이터까지 한 번에 구성됩니다.

-- 테이블 생성 순서는 FK 의존관계를 따릅니다:
--   premier_tiers → ref_maps/ref_agents/ref_weapons → teams → riot_accounts
--   → team_members → matches → match_player_stats → team_stats_summary
--   → player_stats_summary → predictions → insights → rank_snapshots
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
-- 1. PREMIER_TIERS  (프리미어 티어 기준 테이블 - 정적 참조 데이터)
-- ---------------------------------------------------------------------
CREATE TABLE premier_tiers (
    tier_id             INT             NOT NULL AUTO_INCREMENT,
    name_kr             VARCHAR(30)     NOT NULL COMMENT '한글 티어명 (예: 디비전 3)',
    name_en             VARCHAR(30)     NOT NULL COMMENT '영문 티어명',
    sub_division_range  VARCHAR(20)     NULL COMMENT '세부 구간 (예: 1~5)',
    tier_order          INT             NOT NULL COMMENT '정렬 순서 (낮을수록 상위 티어)',
    image_path          VARCHAR(255)    NULL COMMENT '티어 문양 이미지 경로',
    PRIMARY KEY (tier_id),
    UNIQUE KEY uq_premier_tiers_order (tier_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='프리미어 티어 기준 정보';

-- ---------------------------------------------------------------------
-- 2. REF_MAPS / REF_AGENTS / REF_WEAPONS  (요원·무기·맵 GUID 참조 테이블)
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
-- 2-1. REF_PLAYER_CARDS / REF_PLAYER_TITLES  (프로필 아바타/칭호 참조 테이블)
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
-- 3. TEAMS  (팀 단위 계정 - 회원가입/로그인/팀 프로필 겸용)
-- ---------------------------------------------------------------------
CREATE TABLE teams (
    team_id             INT             NOT NULL AUTO_INCREMENT,
    email               VARCHAR(255)    NOT NULL,
    login_id            VARCHAR(50)     NOT NULL,
    password_hash       VARCHAR(255)    NOT NULL,
    privacy_agreed      BOOLEAN         NOT NULL DEFAULT FALSE,
    team_name           VARCHAR(50)     NOT NULL,
    team_tag            VARCHAR(10)     NOT NULL,
    premier_team_id     VARCHAR(64)     NULL COMMENT 'Henrik/Riot 프리미어 team_id (외부 식별자)',
    tier_id             INT             NULL COMMENT 'premier_tiers 참조',
    season              VARCHAR(20)     NULL,
    conference          VARCHAR(50)     NULL,
    division            VARCHAR(20)     NULL,
    ranking_points      INT             NOT NULL DEFAULT 0,
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id),
    UNIQUE KEY uq_teams_login_id (login_id),
    UNIQUE KEY uq_teams_email (email),
    UNIQUE KEY uq_teams_name_tag (team_name, team_tag),
    KEY idx_teams_tier (tier_id),
    CONSTRAINT fk_teams_tier
        FOREIGN KEY (tier_id) REFERENCES premier_tiers (tier_id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀 단위 계정 (개인 로그인 없음, op.gg 스타일)';

-- ---------------------------------------------------------------------
-- 4. RIOT_ACCOUNTS  (로스터 개인 Riot 계정 - 서비스 로그인과 무관)
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
    verification_status ENUM('none','pending','verified','failed')
                                        NOT NULL DEFAULT 'none'
                                        COMMENT '팀 대표 계정만 실질적으로 사용',
    verified_at         DATETIME        NULL,
    updated_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (puuid),
    UNIQUE KEY uq_riot_accounts_name_tag (riot_name, riot_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Riot 개인 계정 (로스터 구성원)';

-- ---------------------------------------------------------------------
-- 5. TEAM_MEMBERS  (팀 로스터 매핑)
-- ---------------------------------------------------------------------
CREATE TABLE team_members (
    team_member_id      INT             NOT NULL AUTO_INCREMENT,
    team_id             INT             NOT NULL,
    puuid               VARCHAR(64)     NOT NULL,
    is_representative   BOOLEAN         NOT NULL DEFAULT FALSE COMMENT '팀 계정 소유 검증 대상',
    is_starter          BOOLEAN         NOT NULL DEFAULT TRUE,
    role_type_override  VARCHAR(20)     NULL COMMENT '역할군 자동매핑 override용',
    joined_at           DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_member_id),
    UNIQUE KEY uq_team_members_team_puuid (team_id, puuid),
    KEY idx_team_members_puuid (puuid),
    CONSTRAINT fk_team_members_team
        FOREIGN KEY (team_id) REFERENCES teams (team_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_team_members_riot_account
        FOREIGN KEY (puuid) REFERENCES riot_accounts (puuid)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀 로스터';

-- ---------------------------------------------------------------------
-- 6. MATCHES  (매치 메타데이터 + 라운드/킬 원본 JSON)
--    ※ map_name(varchar) 대신 map_uuid(FK → ref_maps)로 최종 구성
-- ---------------------------------------------------------------------
CREATE TABLE matches (
    match_id            VARCHAR(64)     NOT NULL COMMENT 'Riot match id (UUID)',
    map_uuid            VARCHAR(64)     NULL COMMENT 'REF_MAPS.uuid 참조',
    mode                VARCHAR(30)     NULL,
    game_start          DATETIME        NULL,
    team_a_id           INT             NULL,
    team_b_id           INT             NULL,
    winner_team_id      INT             NULL,
    round_detail_json   JSON            NULL COMMENT '라운드/킬/데미지 원본 (필요시에만 파싱)',
    api_source          VARCHAR(30)     NULL COMMENT '예: premier_history, v4_matches',
    collected_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (match_id),
    KEY idx_matches_map (map_uuid),
    KEY idx_matches_team_a (team_a_id),
    KEY idx_matches_team_b (team_b_id),
    KEY idx_matches_winner (winner_team_id),
    KEY idx_matches_game_start (game_start),
    CONSTRAINT fk_matches_map
        FOREIGN KEY (map_uuid) REFERENCES ref_maps (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_matches_team_a
        FOREIGN KEY (team_a_id) REFERENCES teams (team_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_matches_team_b
        FOREIGN KEY (team_b_id) REFERENCES teams (team_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_matches_winner
        FOREIGN KEY (winner_team_id) REFERENCES teams (team_id)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='매치 메타데이터';

-- ---------------------------------------------------------------------
-- 7. MATCH_PLAYER_STATS  (매치별 선수 집계 스탯)
--    ※ agent(varchar) → agent_uuid(FK → ref_agents)
--    ※ most_used_weapon(varchar) → most_used_weapon_uuid(FK → ref_weapons)
-- ---------------------------------------------------------------------
CREATE TABLE match_player_stats (
    stat_id                 INT             NOT NULL AUTO_INCREMENT,
    match_id                VARCHAR(64)     NOT NULL,
    puuid                   VARCHAR(64)     NOT NULL,
    team_id                 INT             NULL,
    agent_uuid              VARCHAR(64)     NULL COMMENT 'REF_AGENTS.uuid 참조',
    role_type               VARCHAR(20)     NULL COMMENT '타격대/척후대/감시자/전략가',
    side                    VARCHAR(10)     NULL COMMENT 'Attack/Defense 등',
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
    CONSTRAINT fk_mps_team
        FOREIGN KEY (team_id) REFERENCES teams (team_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_mps_agent
        FOREIGN KEY (agent_uuid) REFERENCES ref_agents (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_mps_weapon
        FOREIGN KEY (most_used_weapon_uuid) REFERENCES ref_weapons (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='매치별 선수 집계 스탯';

-- ---------------------------------------------------------------------
-- 8. TEAM_STATS_SUMMARY  (팀 단위 집계: 맵/사이드/조합 등)
-- ---------------------------------------------------------------------
CREATE TABLE team_stats_summary (
    summary_id          INT             NOT NULL AUTO_INCREMENT,
    team_id             INT             NOT NULL,
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
    UNIQUE KEY uq_team_stats (team_id, stat_type, dimension_key),
    CONSTRAINT fk_tss_team
        FOREIGN KEY (team_id) REFERENCES teams (team_id)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀 단위 집계 통계';

-- ---------------------------------------------------------------------
-- 9. PLAYER_STATS_SUMMARY  (개인 단위 집계: 무기/히트박스/클러치 등)
-- ---------------------------------------------------------------------
CREATE TABLE player_stats_summary (
    summary_id          INT             NOT NULL AUTO_INCREMENT,
    puuid               VARCHAR(64)     NOT NULL,
    stat_type           ENUM('weapon','hitbox','clutch','role_matchup','engagement')
                                        NOT NULL,
    dimension_key       VARCHAR(100)    NOT NULL
        COMMENT 'stat_type=weapon일 때 REF_WEAPONS.uuid를 값으로 사용 (폴리모픽이라 강한 FK 없음). 예: Head, 1v1',
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
-- 10. PREDICTIONS  (승부 예측 결과 - Layer1 모델 산출값)
--     ※ map_name(varchar) → map_uuid(FK → ref_maps)
-- ---------------------------------------------------------------------
CREATE TABLE predictions (
    prediction_id       INT             NOT NULL AUTO_INCREMENT,
    team_a_id           INT             NOT NULL,
    team_b_id           INT             NOT NULL,
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
    CONSTRAINT fk_predictions_team_a
        FOREIGN KEY (team_a_id) REFERENCES teams (team_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_predictions_team_b
        FOREIGN KEY (team_b_id) REFERENCES teams (team_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_predictions_map
        FOREIGN KEY (map_uuid) REFERENCES ref_maps (uuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='승부 예측 모델(Layer1) 결과';

-- ---------------------------------------------------------------------
-- 11. INSIGHTS  (AI 리포트 - 팀/개인 서술형 결과, Layer2)
-- ---------------------------------------------------------------------
CREATE TABLE insights (
    insight_id          INT             NOT NULL AUTO_INCREMENT,
    team_id             INT             NOT NULL,
    opponent_team_id    INT             NULL COMMENT '매치업 리포트일 때만 사용',
    target_type         ENUM('team','player')  NOT NULL DEFAULT 'team',
    target_puuid        VARCHAR(64)     NULL COMMENT 'target_type=player일 때만 사용',
    insight_type        VARCHAR(30)     NULL COMMENT 'weakness, strategy, personal_feedback, agent_comment',
    content              TEXT           NOT NULL,
    generated_at         DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (insight_id),
    KEY idx_insights_team (team_id),
    KEY idx_insights_opponent (opponent_team_id),
    KEY idx_insights_target_puuid (target_puuid),
    CONSTRAINT fk_insights_team
        FOREIGN KEY (team_id) REFERENCES teams (team_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_insights_opponent
        FOREIGN KEY (opponent_team_id) REFERENCES teams (team_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_insights_target_puuid
        FOREIGN KEY (target_puuid) REFERENCES riot_accounts (puuid)
        ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='AI 리포트(Layer2) - 팀/개인 서술형 결과';

-- ---------------------------------------------------------------------
-- 12. RANK_SNAPSHOTS  (팀/개인 랭크 추이 - 폴리모픽 참조)
-- ---------------------------------------------------------------------
-- owner_type + owner_id 조합으로 teams.team_id 또는 riot_accounts.puuid를
-- 가리키는 폴리모픽 구조입니다. 대상 테이블이 둘로 나뉘어 있어
-- 일반적인 단일 FK 제약을 걸 수 없으므로, 무결성은 애플리케이션(백엔드) 레벨에서
-- 보장해야 합니다 (owner_type='team'이면 teams.team_id, 'player'면 riot_accounts.puuid 존재 검증).
CREATE TABLE rank_snapshots (
    snapshot_id         INT             NOT NULL AUTO_INCREMENT,
    owner_type          ENUM('team','player')  NOT NULL,
    owner_id            VARCHAR(64)     NOT NULL COMMENT 'team_id 또는 puuid (폴리모픽, FK 제약 없음)',
    tier_or_division    VARCHAR(30)     NULL,
    points              INT             NULL,
    snapshot_at         DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_id),
    KEY idx_rank_snapshots_owner (owner_type, owner_id, snapshot_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='팀/개인 랭크·RP 추이 스냅샷 (폴리모픽)';

-- =====================================================================
-- 참고: 자주 쓰게 될 조인 예시
--
-- 매치 선수 스탯을 사람이 읽을 수 있는 이름으로 조회:
-- SELECT mps.stat_id, ra.display_name AS agent_name, ra.role_type,
--        rw.display_name AS weapon_name, m.map_uuid, rm.display_name AS map_name
-- FROM match_player_stats mps
-- LEFT JOIN ref_agents  ra ON mps.agent_uuid = ra.uuid
-- LEFT JOIN ref_weapons rw ON mps.most_used_weapon_uuid = rw.uuid
-- JOIN matches m ON mps.match_id = m.match_id
-- LEFT JOIN ref_maps rm ON m.map_uuid = rm.uuid;
-- =====================================================================
-- 끝
-- =====================================================================