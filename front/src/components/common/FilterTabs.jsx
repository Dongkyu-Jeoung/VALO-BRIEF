/**
 * 공용 필터 탭. tabs=["통계","분석","AI 리포트"] 처럼 넘기면
 * 승부예측(3탭)/우리팀분석(4탭) 어디에도 그대로 재사용 가능합니다.
 */
export default function FilterTabs({ tabs, activeTab, onChange }) {
  return (
    <div className="filter-tabs-row">
      <div className="filter-tabs">
        {tabs.map((tab) => (
          <button
            key={tab}
            className={`filter-tab ${tab === activeTab ? 'on' : ''}`}
            onClick={() => onChange(tab)}
            type="button"
          >
            {tab}
          </button>
        ))}
      </div>
    </div>
  );
}
