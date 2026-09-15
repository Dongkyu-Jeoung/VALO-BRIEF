import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { fetchTeamAiReport, fetchTeamAnalysis, fetchTeamProfile } from '../../api/teams';
import { fetchPrediction, fetchRecentOpponent } from '../../api/prediction';
import { DEMO_TEAM_NAME, DEMO_TEAM_TAG } from '../../constants/demoTeam';
import { useAuth } from '../../context/AuthContext';
import PredictBox from '../../components/predict/PredictBox';
import FilterTabs from '../../components/common/FilterTabs';
import { TeamProfileBody } from '../TeamProfilePage';
import AnalysisTab from './AnalysisTab';
import AiReportTab from './AiReportTab';
import LoadingText from '../../components/common/LoadingText';

const TABS = ['통계', '분석', 'AI 리포트'];

export default function MatchPredictionPage() {
  const { teamName, teamTag } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isAuthenticated } = useAuth();

  const activeTab = TABS.includes(searchParams.get('tab')) ? searchParams.get('tab') : '통계';

  const [analysisData, setAnalysisData] = useState(null);
  const [opponentTeam, setOpponentTeam] = useState(null);
  // 우리팀(로그인한 팀) vs 상대팀 승률 예측 - /api/predict/{team_name}/{team_tag}가
  // JWT로 로그인한 팀을 "우리팀"으로 자동 인식해서 실제 모델(XGBoost)을 돌린다.
  const [prediction, setPrediction] = useState(null);
  const [predictionError, setPredictionError] = useState(null);
  // resolveOpponent()가 실제로 확정한 상대팀 name/tag - 데모 링크 자동 치환(최근 상대로
  // 바뀔 수 있음) 이후의 값이라 URL의 teamName/teamTag와 다를 수 있다. AI 리포트 탭이
  // 지연 로딩(activeTab이 바뀔 때 따로 fetch)이라 이 값을 따로 들고 있어야 한다.
  const [resolvedOpponent, setResolvedOpponent] = useState(null);
  const [aiReport, setAiReport] = useState(null);
  // 백엔드 status 그대로("ready"/"not_ready"/"generating") - AiReportTab이 이 값으로
  // 세 가지 화면(리포트/준비 중 안내/생성 중 안내)을 구분한다.
  const [aiReportStatus, setAiReportStatus] = useState(null);
  // fetchTeamAiReport가 5xx(LLM 호출 실패 등 실제 서버 장애)를 재던지는 경우를 위한
  // 에러 메시지 - status 기반 3분기(ready/not_ready/generating)와 별개로 "요청 자체가
  // 실패했다"는 네 번째 상태를 표현한다(2026-09-15, api/teams.js::fetchTeamAiReport
  // 참고). null이면 정상 status 분기를 그대로 사용한다.
  const [aiReportError, setAiReportError] = useState(null);
  // aiReport는 정상적으로 null일 수 있어서(상대팀 데이터가 아직 준비 안 됨) "아직 요청
  // 자체를 안 보냈다"와 구분하는 별도 플래그가 필요하다 - 없으면 null인 동안 매 렌더마다
  // 계속 재요청하게 된다.
  const [aiReportRequested, setAiReportRequested] = useState(false);
  const [aiReportSettled, setAiReportSettled] = useState(false);

  useEffect(() => {
    let active = true;

    // 상대가 바뀌면 이전 예측과 새 프로필이 함께 표시되지 않도록 초기화한다.
    setPrediction(null);
    setPredictionError(null);
    setOpponentTeam(null);
    setAnalysisData(null);
    setResolvedOpponent(null);
    setAiReport(null);
    setAiReportStatus(null);
    setAiReportError(null);
    setAiReportRequested(false);
    setAiReportSettled(false);

    // 로그인 전: URL의 팀(데모 링크는 실존하지 않는 team-ascend라 자동으로 mock 폴백된다).
    // 로그인 후 + URL이 기본 데모 링크(네비 메뉴/홈 카드가 항상 이 팀으로 연결)일 때만
    // 상대팀을 우리 팀의 "가장 최근에 매치했던 팀"으로 자동 설정한다 - 최근 상대를 못
    // 찾으면(매치 이력 없음 등) URL의 팀으로 그냥 둔다.
    // 헤더 검색창으로 실제 팀을 검색해 들어온 경우(URL이 데모 링크가 아님)는 이 자동
    // 대체를 건너뛰고 검색된 팀을 그대로 존중한다 - 안 그러면 로그인 상태에서 팀을
    // 검색해도 매번 "내 최근 상대팀"으로 덮어써져서 검색한 팀이 안 뜨는 버그가 있었다.
    async function resolveOpponent() {
      const isDemoLink = teamName === DEMO_TEAM_NAME && teamTag === DEMO_TEAM_TAG;
      if (!isAuthenticated || !isDemoLink) return { teamName, teamTag };
      const recent = await fetchRecentOpponent();
      return recent ? { teamName: recent.teamName, teamTag: recent.teamTag } : { teamName, teamTag };
    }

    resolveOpponent().then(({ teamName: name, teamTag: tag }) => {
      if (!active) return;
      setResolvedOpponent({ name, tag });

      fetchTeamAnalysis(name, tag).then((data) => {
        if (active && data) {
          // [안전 매핑] 백엔드 키와 프론트엔드 키 불일치로 인한 undefined 방지
          const normalizedData = {
            ...data,
            roundInfo: {
              attackWinRate: data.roundInfo?.attackWinRate ?? data.roundInfo?.atkWinRate ?? 0,
              defenseWinRate: data.roundInfo?.defenseWinRate ?? data.roundInfo?.defWinRate ?? 0,
              pistolWinRate: data.roundInfo?.pistolWinRate ?? 0,
              ecoWinRate: data.roundInfo?.ecoWinRate ?? 0,
              fbWinRate: data.roundInfo?.fbWinRate ?? 0,
              fdLoseRate: data.roundInfo?.fdLoseRate ?? 0,
            }
          };
          setAnalysisData(normalizedData);
        }
      });
      fetchTeamProfile(name, tag).then((data) => { if (active) setOpponentTeam(data); });
      fetchPrediction(name, tag)
        .then((data) => { if (active) setPrediction(data); })
        .catch((err) => {
          if (!active) return;
          let message = '승부예측을 진행할 수 없습니다.';
          try {
            const body = JSON.parse(err.message.replace(/^\[HTTP \d+\]\s*/, ''));
            if (typeof body.detail === 'string') message = body.detail;
          } catch { /* 기본 안내 문구 사용 */ }
          setPredictionError(message);
        });
    });

    return () => { active = false; };
  }, [teamName, teamTag, isAuthenticated]);

  // AI 리포트는 비용이 큰 LLM 호출이라(services/opponent_ai_report.py) 탭을 처음 열 때만
  // 지연 조회한다(MyTeamAnalysisPage와 동일한 패턴). resolvedOpponent가 정해지기 전엔
  // 대기 - 데모 링크 자동 치환 중에 URL의 teamName/teamTag로 잘못 조회하지 않기 위함.
  // 이 트리거는 "시작 여부"만 결정한다(activeTab에 의존) - 실제 폴링 루프는 아래
  // 별도 effect가 맡는다(activeTab에 의존하지 않음, 이유는 그 effect 주석 참고).
  useEffect(() => {
    if (activeTab !== 'AI 리포트' || aiReportRequested || !resolvedOpponent) return;
    setAiReportRequested(true);
  }, [activeTab, aiReportRequested, resolvedOpponent]);

  // 백엔드가 캐시된 리포트가 없으면 즉시 {"status":"generating"}으로 응답하고 Claude
  // 생성은 백그라운드로 넘긴다(services/opponent_ai_report.py 참고, 20~45초 걸림) - 여기서
  // 몇 초 간격으로 다시 조회해 완료 여부를 확인한다. activeTab을 의존성에 넣지 않는 이유:
  // 백엔드 생성은 탭 전환과 무관하게 계속 진행되므로, "통계" 탭으로 잠깐 넘어갔다 돌아와도
  // 폴링이 끊기지 않고 이어져야 한다(넣으면 탭을 벗어나는 순간 클린업으로 폴링이 멈추고,
  // aiReportRequested는 이미 true라 다시 안 돌아 영구히 멈춰버리는 문제가 있었다).
  useEffect(() => {
    if (!aiReportRequested || !resolvedOpponent) return;
    let active = true;
    let timer = null;

    async function poll() {
      // fetchTeamAiReport는 이제 5xx(LLM 호출 실패 등 실제 서버 장애)를 mock으로
      // 덮지 않고 그대로 던진다(2026-09-15, api/teams.js 참고) - 여기서 안 잡으면
      // 처리 안 된 예외로 폴링이 조용히 멈추고 "AI 리포트" 탭이 로딩 상태로 영원히
      // 멈춘 것처럼 보인다. predictionError와 같은 패턴으로 명확한 에러 메시지를
      // 상태에 담아 화면에 보여준다.
      try {
        const data = await fetchTeamAiReport(resolvedOpponent.name, resolvedOpponent.tag);
        if (!active) return;
        const status = data?.status ?? 'not_ready';
        setAiReportStatus(status);
        setAiReport(status === 'ready' ? data.report : null);
        setAiReportSettled(true);
        if (status === 'generating') {
          timer = setTimeout(poll, 4000);
        }
      } catch {
        if (!active) return;
        setAiReportError('AI 리포트를 불러올 수 없습니다. 잠시 후 다시 시도해 주세요.');
        setAiReportSettled(true);
      }
    }
    poll();

    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [aiReportRequested, resolvedOpponent]);

  // 승률은 프로필·분석 요청의 완료를 기다리지 않고 먼저 표시한다.
  if (predictionError) {
    return (
      <div className="error-state" role="alert">
        <span className="error-state__message">{predictionError}</span>
      </div>
    );
  }
  if (!prediction) return <LoadingText full />;

  // 로그인 상태인데도 /api/predict가 실패(최근 매치 로스터 5인을 못 찾는 등)해서
  // predictionMock으로 폴백하면 우리팀 이름까지 mock("Team Phoenix")으로 보일 수 있다 -
  // 그 경우에도 이름/태그만큼은 로그인한 팀 정보로 덮어써서 보여준다.
  const ourTeam = user
    ? {
        ...prediction.ourTeam,
        name: user.teamName,
        tag: user.teamTag,
        avgWinRate20:
          prediction.blue_summary?.winrate
          ?? prediction.ourTeam?.avgWinRate20
          ?? 0,
      }
    : {
        ...prediction.ourTeam,
        avgWinRate20:
          prediction.blue_summary?.winrate
          ?? prediction.ourTeam?.avgWinRate20
          ?? 0,
      };

  const displayOpponentTeam = {
    name: teamName,
    tag: teamTag,
    ...prediction.opponentTeam,
    ...opponentTeam,

    avgWinRate20:
      prediction.red_summary?.winrate
      ?? prediction.opponentTeam?.avgWinRate20
      ?? opponentTeam?.avgWinRate20
      ?? 0,
  };

  return (
    <div className="page-container">
      <PredictBox
        ourTeam={ourTeam}
        opponentTeam={displayOpponentTeam}
        ourWinChance={
          prediction.blue_win_probability
          ?? prediction.ourWinChance
          ?? 0
        }
      />

      <FilterTabs tabs={TABS} activeTab={activeTab} onChange={(tab) => setSearchParams({ tab })} />

      {activeTab === '통계' ? (
        opponentTeam ? <TeamProfileBody team={opponentTeam} /> : <LoadingText />
      ) : null}
      {activeTab === '분석' ? (
        analysisData ? <AnalysisTab analysis={analysisData} /> : <LoadingText />
      ) : null}
      {activeTab === 'AI 리포트' ? (
        aiReportSettled ? (
          aiReportError ? (
            <div className="error-state" role="alert">
              <span className="error-state__message">{aiReportError}</span>
            </div>
          ) : (
            <AiReportTab report={aiReport} status={aiReportStatus} opponentName={displayOpponentTeam.name} />
          )
        ) : <LoadingText />
      ) : null}
    </div>
  );
}